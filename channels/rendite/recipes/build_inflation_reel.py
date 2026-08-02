"""Custom comparison REEL: Germany's July 2026 inflation jump (2.3% -> 2.8%),
what drives it (energy +8.3%) and what it does to savings (real rate, and the
spread between average and best overnight-deposit rates). Bright colorful opener
(woman at a citrus stand) + colorful paint CTA, four branded frames, fluent
hand-written voiceover. Educational only, no advice.

Sources (verified 31.07.2026): Destatis PM (DE July CPI +2.8%, core +2.4%,
energy +8.3%, m/m +0.8%), Eurostat flash (EA 2.9%, core 2.5%), ECB deposit
rate 2.25% (meeting 23.07.2026), average overnight deposit rate 1.95% p.a.,
best offers up to 4.00% p.a.
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

# ── livelier, natural voice (process-local, playbook defaults) ──────────────
config.ELEVENLABS_STABILITY = 0.40
config.ELEVENLABS_STYLE = 0.40
config.ELEVENLABS_SPEED = 1.06

# opener: woman picking citrus at a bright market stall (clear hero, warm+colorful)
_OPENER_ID = int(os.getenv("OPENER_ID", "9474086"))
_CTA_ID = int(os.getenv("CTA_ID", "9668305"))  # bright colorful paint (proven)

W, H = 1080, 1920
F = branding.load_font
BG, CARD, BLUE, BLUEL, FG, MUTED = (branding.BG, branding.CARD, branding.BLUE,
                                    branding.BLUE_LIGHT, branding.FG, branding.MUTED)
RED, GREEN, AMBER = branding.RED, branding.GREEN, branding.AMBER

STAND = "Stand: 31. Juli 2026 · Quelle: Destatis / Eurostat"


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


# IG overlays the top ~290px (profile name) and subtitles sit at MarginV=500
# (~y1260-1420) → all content stays inside y≈290–1250.
TOP = 290


def _kicker(d, text, color=BLUE):
    f = F(34, bold=True)
    tw = d.textlength(text, font=f)
    d.rounded_rectangle((60, TOP, 60 + tw + 46, TOP + 62), radius=16, fill=color)
    d.text((60 + 23, TOP + 12), text, font=f, fill=(255, 255, 255))


def _title(d, text, y=TOP + 84, size=56, color=FG):
    d.text((60, y), text, font=F(size, bold=True), fill=color)


def _stand(d, y):
    d.text((60, y), STAND, font=F(24), fill=MUTED)


def _footer(d):
    d.line((60, H - 118, W - 60, H - 118), fill=MUTED, width=2)
    d.text((60, H - 102), "Keine Anlageberatung · keine Kauf-/Verkaufsempfehlung · Werbung",
           font=F(23), fill=MUTED)


def _rtext(d, right_x, y, text, font, fill):
    d.text((right_x - d.textlength(text, font=font), y), text, font=font, fill=fill)


def _ctext(d, cx, y, text, font, fill):
    d.text((cx - d.textlength(text, font=font) / 2, y), text, font=font, fill=fill)


def _save(img, name) -> str:
    out = Path(config.OUTPUT_DIR) / name
    img.save(out, quality=92)
    return str(out)


def frame_numbers() -> str:
    """The fresh numbers: DE, euro area, core, ECB target."""
    img, d = _canvas()
    _kicker(d, "DIE NEUEN ZAHLEN")
    _title(d, "Die Preise ziehen wieder an")
    _stand(d, TOP + 158)
    rows = [("Deutschland", "Juli 2026", "2,8 %", RED, "Juni: 2,3 %"),
            ("Eurozone", "Juli 2026", "2,9 %", RED, "Juni: 2,8 %"),
            ("Kernrate DE", "ohne Energie & Lebensmittel", "2,4 %", AMBER, ""),
            ("Ziel der EZB", "seit Jahren unverändert", "2,0 %", GREEN, "")]
    y, ch, gap = 490, 146, 16
    for name, sub, val, col, note in rows:
        d.rounded_rectangle((60, y, W - 60, y + ch), radius=22, fill=CARD)
        d.text((92, y + 24), name, font=F(42, bold=True), fill=FG)
        d.text((92, y + 84), sub, font=F(27), fill=MUTED)
        _rtext(d, W - 92, y + 26, val, F(58, bold=True), col)
        if note:
            _rtext(d, W - 92, y + 96, note, F(26), MUTED)
        y += ch + gap
    y += 8
    branding.wrap(d, "In nur einem Monat: ein halber Prozentpunkt mehr Teuerung.",
                  F(31), 60, y, 48, MUTED, 42)
    _footer(d)
    return _save(img, "infl_frame_numbers.jpg")


def frame_driver() -> str:
    """Where the jump comes from: energy."""
    img, d = _canvas()
    _kicker(d, "DER TREIBER")
    _title(d, "Fast alles kommt aus")
    _title(d, "einer einzigen Ecke", y=TOP + 150)
    rows = [("Energie", "Strom · Gas · Sprit", "+8,3 %", RED),
            ("Ohne Energie & Lebensmittel", "die sogenannte Kernrate", "+2,4 %", AMBER),
            ("Preise ggü. Juni", "nur ein Monat", "+0,8 %", RED)]
    y, ch, gap = 526, 148, 16
    for name, sub, val, col in rows:
        d.rounded_rectangle((60, y, W - 60, y + ch), radius=22, fill=CARD)
        d.text((92, y + 24), name, font=F(36, bold=True), fill=FG)
        d.text((92, y + 80), sub, font=F(27), fill=MUTED)
        _rtext(d, W - 92, y + 38, val, F(54, bold=True), col)
        y += ch + gap
    y += 12
    d.rounded_rectangle((60, y, W - 60, y + 196), radius=20, fill=(24, 32, 44))
    d.text((92, y + 22), "Warum das wichtig ist", font=F(30, bold=True), fill=BLUEL)
    branding.wrap(d, "Die Kernrate liegt UNTER der Gesamtrate. Der Schub kommt also "
                     "nicht aus der Breite, sondern aus der Energie.",
                  F(31), 92, y + 74, 44, FG, 44)
    _footer(d)
    return _save(img, "infl_frame_driver.jpg")


def frame_savings() -> str:
    """What 2.8% does to savings: the real rate."""
    img, d = _canvas()
    _kicker(d, "DEIN ERSPARTES")
    _title(d, "Was 2,8 % mit deinem")
    _title(d, "Geld machen", y=TOP + 150)
    rows = [("Tagesgeld im Schnitt", "1,95 %", BLUEL, "+"),
            ("Inflation im Juli", "2,8 %", RED, "−"),
            ("Bleibt real übrig", "−0,85 %", RED, "=")]
    y, ch, gap = 566, 140, 16
    for name, val, col, sign in rows:
        d.rounded_rectangle((60, y, W - 60, y + ch), radius=22, fill=CARD)
        d.text((92, y + 40), sign, font=F(44, bold=True), fill=MUTED)
        d.text((160, y + 44), name, font=F(38, bold=True), fill=FG)
        _rtext(d, W - 92, y + 34, val, F(56, bold=True), col)
        y += ch + gap
    y += 12
    d.rounded_rectangle((60, y, W - 60, y + 190), radius=20, fill=(44, 24, 28))
    d.text((92, y + 24), "Konkret bei 10.000 Euro", font=F(30, bold=True), fill=RED)
    branding.wrap(d, "Rund 85 Euro Kaufkraft weniger — pro Jahr. Das Geld auf dem "
                     "Konto bleibt gleich, kaufen kannst du dafür weniger.",
                  F(31), 92, y + 74, 44, FG, 44)
    _footer(d)
    return _save(img, "infl_frame_savings.jpg")


def frame_spread() -> str:
    """The aha: average vs best offer — same risk, 205 EUR apart."""
    img, d = _canvas()
    _kicker(d, "DER UNTERSCHIED", GREEN)
    _title(d, "Gleiches Risiko —")
    _title(d, "205 Euro Unterschied", y=TOP + 150)
    _stand(d, TOP + 232)
    cards = [("Durchschnitts-Tagesgeld", "1,95 %", "real −0,85 %", "−85 € im Jahr", RED),
             ("Bestes Tagesgeld-Angebot", "4,00 %", "real +1,20 %", "+120 € im Jahr", GREEN)]
    y, ch, gap = 574, 216, 22
    for name, rate, real, euro, col in cards:
        d.rounded_rectangle((60, y, W - 60, y + ch), radius=22, fill=CARD)
        d.text((92, y + 22), name, font=F(34, bold=True), fill=FG)
        d.text((92, y + 86), rate, font=F(64, bold=True), fill=col)
        _rtext(d, W - 92, y + 90, real, F(34, bold=True), MUTED)
        _rtext(d, W - 92, y + 140, euro, F(40, bold=True), col)
        y += ch + gap
    y += 6
    d.rounded_rectangle((60, y, W - 60, y + 170), radius=20, fill=(20, 40, 32))
    d.text((92, y + 22), "Bei 10.000 Euro", font=F(30, bold=True), fill=GREEN)
    branding.wrap(d, "205 Euro Unterschied im Jahr — allein durch die Wahl des Kontos, "
                     "bei identischer Einlagensicherung.",
                  F(31), 92, y + 70, 44, FG, 44)
    _footer(d)
    return _save(img, "infl_frame_spread.jpg")


# Voiceover: numbers ALWAYS written as words (engine slurs bare digits),
# dates spoken out (reels stay online).
_TEXTS = [
    "Am einunddreißigsten Juli kam die Zahl, die hier wirklich jeden betrifft. "
    "Die Inflation in Deutschland ist im Juli auf zwei Komma acht Prozent gesprungen. "
    "Im Juni waren es noch zwei Komma drei.",

    "Das ist ein ordentlicher Satz nach oben. In der gesamten Eurozone liegt die Teuerung "
    "bei zwei Komma neun Prozent. Das Ziel der Europäischen Zentralbank sind zwei Prozent, "
    "davon sind wir wieder ein gutes Stück entfernt.",

    "Der Sprung kommt fast komplett aus einer einzigen Ecke, und das ist die Energie. "
    "Strom, Gas und Sprit kosten acht Komma drei Prozent mehr als vor einem Jahr. "
    "Rechnet man Energie und Lebensmittel heraus, bleiben nur zwei Komma vier Prozent übrig.",

    "Für dein Geld heißt das ganz konkret: Das durchschnittliche Tagesgeld bringt gerade "
    "knapp zwei Prozent. Bei zwei Komma acht Prozent Inflation schrumpft dein Erspartes real. "
    "Bei zehntausend Euro sind das rund fünfundachtzig Euro Kaufkraft im Jahr.",

    "Und jetzt der Teil, den die meisten übersehen. Die besten Tagesgeld-Angebote liegen bei "
    "vier Prozent. Zwischen Durchschnitt und Bestangebot liegen gut zwei Prozentpunkte. "
    "Bei zehntausend Euro macht das über zweihundert Euro im Jahr aus, bei genau demselben Risiko.",

    "Weißt du, wie viel Zinsen dein Tagesgeld gerade bringt? Schreib es in die Kommentare "
    "und folge für den echten Durchblick bei deinem Geld!",
]

_TITLE = "Inflation zurück: Was 2,8 % mit deinem Ersparten machen"

_CAPTION = (
    "📈 Die Inflation ist zurück — und sie kostet dich Geld.\n\n"
    "Am 31. Juli 2026 kamen die frischen Zahlen:\n"
    "🇩🇪 Deutschland: 2,8 % (Juni: 2,3 %)\n"
    "🇪🇺 Eurozone: 2,9 % (Juni: 2,8 %)\n"
    "🔌 Energie: +8,3 % zum Vorjahr\n"
    "📊 Kernrate ohne Energie & Lebensmittel: 2,4 %\n"
    "🎯 Ziel der EZB: 2,0 %\n\n"
    "Interessant: Die Kernrate liegt UNTER der Gesamtrate — der Schub kommt aus der "
    "Energie, nicht aus der Breite.\n\n"
    "Was das mit dem Ersparten macht:\n"
    "💰 Tagesgeld im Schnitt: 1,95 %\n"
    "➖ Inflation: 2,8 %\n"
    "= real −0,85 % → bei 10.000 € rund 85 € Kaufkraft weniger pro Jahr\n\n"
    "Und der Unterschied, den kaum jemand nutzt: Die besten Tagesgeld-Angebote liegen bei "
    "rund 4,0 %. Das sind bei 10.000 € über 200 € Unterschied im Jahr — bei identischer "
    "Einlagensicherung.\n\n"
    "Wie viel Zinsen bringt dein Tagesgeld gerade? 👇\n\n"
    "⚠️ Keine Anlageberatung — nur Bildung & Unterhaltung. Kein Kauf-/Verkaufsaufruf.\n"
    "Quellen: Destatis & Eurostat (31.07.2026), EZB-Einlagensatz 2,25 %.\n"
    "#inflation #tagesgeld #zinsen #sparen #kaufkraft #finanzen #geldanlage #ezb "
    "#finanzwissen #börse"
)


async def _main() -> None:
    opener = _ensure_clip(_OPENER_ID)
    cta = _ensure_clip(_CTA_ID)
    frames = [frame_numbers(), frame_driver(), frame_savings(), frame_spread()]
    broll_paths = [opener, frames[0], frames[1], frames[2], frames[3], cta]

    segments = [ScriptSegment(text=t, broll_query="") for t in _TEXTS]
    script = ReelScript(hook=_TEXTS[0], segments=segments, caption=_CAPTION,
                        hashtags=[], title=_TITLE)

    with session_scope() as s:
        reel = ReelRow(trend_id=0,
                       script_json=json.dumps({"topic": "german inflation july 2026",
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
    print(f"Inflations-Reel #{rid} fertig: {video}")

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
