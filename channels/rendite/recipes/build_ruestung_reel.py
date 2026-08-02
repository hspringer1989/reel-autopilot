"""Custom REEL: die Rüstungs-Rallye — wer verdient am globalen Aufrüsten? Player nach
Land, der Boom-Treiber (NATO/Trump/Europa-Aufrüstung), Aktien-Vergleich, Chance/Risiko.
Opener: gepanzertes Militärfahrzeug (Hero). Vier Marken-Frames im Safe-Band, fluente
Stimme. Setzt einen echten `title` im script_json → korrekte 'NEUES REEL'-Ankündigung.
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

_OPENER_ID = int(os.getenv("OPENER_ID", "17502682"))  # armored military vehicle / weapon station
_CTA_ID = int(os.getenv("CTA_ID", "9668305"))          # bright colorful paint
_TITLE = "Die Rüstungs-Rallye: Wer verdient am Aufrüsten?"

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


def frame_powers() -> str:
    img, d = _canvas()
    _kicker(d, "DIE RÜSTUNGS-WELTMÄCHTE")
    _title(d, "Wer rüstet die Welt aus?")
    rows = [("USA", "Raketen & Jets", "RTX · Lockheed · Northrop"),
            ("Großbritannien", "Marine & Systeme", "BAE Systems"),
            ("Deutschland", "Panzer & Munition", "Rheinmetall"),
            ("Frankreich", "Elektronik & Jets", "Thales · Dassault")]
    y, ch, gap = 476, 168, 16
    for country, seg, comps in rows:
        d.rounded_rectangle((60, y, W - 60, y + ch), radius=22, fill=CARD)
        d.text((92, y + 22), country, font=F(42, bold=True), fill=FG)
        _rtext(d, W - 92, y + 30, seg, F(28, bold=True), BLUEL)
        d.text((92, y + 82), comps, font=F(30), fill=MUTED)
        y += ch + gap
    _footer(d)
    return _save(img, "ru_frame_powers.jpg")


def frame_driver() -> str:
    img, d = _canvas()
    _kicker(d, "DER BOOM-TREIBER")
    _title(d, "Warum jetzt?")
    rows = [("Europas Ausgaben seit 2019", "×2"),
            ("NATO-Ziel (Trump drängt)", "5 % vom BIP"),
            ("Bis 2030 (Europa)", "~800 Mrd €")]
    y, ch, gap = 476, 130, 16
    for label, val in rows:
        d.rounded_rectangle((60, y, W - 60, y + ch), radius=20, fill=CARD)
        d.text((92, y + 44), label, font=F(33, bold=True), fill=FG)
        _rtext(d, W - 92, y + 38, val, F(44, bold=True), BLUEL)
        y += ch + gap
    y += 8
    d.rounded_rectangle((60, y, W - 60, y + 190), radius=20, fill=(30, 30, 40))
    d.text((92, y + 24), "Konkret", font=F(30, bold=True), fill=BLUEL)
    branding.wrap(d, "Deutschland steigert von 108 Mrd € (2026) auf 152 Mrd € (2029). "
                     "Die Auftragsbücher sind randvoll.",
                  F(33), 92, y + 78, 42, FG, 46)
    _footer(d)
    return _save(img, "ru_frame_driver.jpg")


def frame_valuation() -> str:
    img, d = _canvas()
    _kicker(d, "AKTIEN IM VERGLEICH")
    _title(d, "Groß gegen schnell")
    rows = [("RTX", "USA", "251 Mrd $"), ("BAE Systems", "UK", "78 Mrd $"),
            ("Rheinmetall", "DE", "53 Mrd $")]
    y, ch, gap = 476, 118, 16
    for name, land, val in rows:
        d.rounded_rectangle((60, y, W - 60, y + ch), radius=18, fill=CARD)
        d.text((90, y + 38), name, font=F(38, bold=True), fill=FG)
        d.text((470, y + 44), land, font=F(28), fill=MUTED)
        _rtext(d, W - 90, y + 38, val, F(40, bold=True), BLUEL)
        y += ch + gap
    y += 8
    d.rounded_rectangle((60, y, W - 60, y + 200), radius=20, fill=(30, 30, 40))
    d.text((92, y + 24), "Der Kick", font=F(30, bold=True), fill=RED)
    branding.wrap(d, "Rheinmetall: plus 15 % in einer Woche (NATO-Gipfel), aber noch rund "
                     "ein Drittel unter dem Jahresstart — hohe Schwankung.",
                  F(32), 92, y + 78, 42, FG, 44)
    _footer(d)
    return _save(img, "ru_frame_valuation.jpg")


def frame_stakes() -> str:
    img, d = _canvas()
    _kicker(d, "CHANCE & RISIKO")
    _title(d, "Boom oder Blase?")
    rows = [("Chance", "Jahrzehnt-Aufrüstung → volle Auftragsbücher", GREEN),
            ("Risiko", "Hohe Bewertung, Vola, politische Rückschläge", RED)]
    y, ch, gap = 476, 170, 20
    for tag, txt, col in rows:
        d.rounded_rectangle((60, y, W - 60, y + ch), radius=20, fill=CARD)
        d.ellipse((92, y + 40, 92 + 34, y + 74), fill=col)
        d.text((150, y + 34), tag, font=F(40, bold=True), fill=col)
        d.text((92, y + 96), txt, font=F(29), fill=FG)
        y += ch + gap
    y += 14
    branding.wrap(d, "Struktureller Rückenwind trifft sportliche Bewertung — der Trend ist "
                     "stark, aber kein Selbstläufer. Beobachten, nicht hinterherlaufen.",
                  F(31), 90, y, 44, MUTED, 42)
    _footer(d)
    return _save(img, "ru_frame_stakes.jpg")


_TEXTS = [
    "Rüstungsaktien sind gerade der heißeste Trade Europas. Zeit zu verstehen, wer am "
    "weltweiten Aufrüsten wirklich verdient.",
    "Die USA dominieren mit Riesen wie RTX und Lockheed. In Europa sind es BAE aus "
    "Großbritannien, Rheinmetall aus Deutschland und Thales aus Frankreich.",
    "Der Treiber: Europa hat seine Verteidigungsausgaben seit 2019 verdoppelt, Kurs auf "
    "achthundert Milliarden Euro bis 2030. Die USA drängen sogar auf fünf Prozent vom "
    "Bruttoinlandsprodukt.",
    "Im Vergleich zeigt sich die Spannung: RTX ist über zweihundertfünfzig Milliarden "
    "Dollar wert, Rheinmetall gut fünfzig. Rheinmetall sprang zuletzt fünfzehn Prozent in "
    "einer Woche, liegt aber seit Jahresbeginn noch ein Drittel im Minus.",
    "Unterm Strich: Das jahrzehntelange Aufrüsten ist echter Rückenwind mit vollen "
    "Auftragsbüchern. Das Risiko sind die hohen Bewertungen und politische Rückschläge.",
    "Rüstung ins Depot, ja oder nein? Schreib es in die Kommentare und folge für ehrliche "
    "Branchen-Analysen!",
]

_CAPTION = (
    "🪖 Die Rüstungs-Rallye: Wer verdient wirklich am globalen Aufrüsten?\n\n"
    "Rüstungsaktien sind der heißeste Trade Europas — angetrieben vom NATO-Gipfel und "
    "Trumps Druck auf 5 % vom BIP.\n\n"
    "🌍 Die Player nach Land:\n"
    "🇺🇸 USA: RTX (~251 Mrd $), Lockheed, Northrop\n"
    "🇬🇧 UK: BAE Systems (~78 Mrd $)\n"
    "🇩🇪 DE: Rheinmetall (~53 Mrd $) — Panzer & Munition\n"
    "🇫🇷 FR: Thales, Dassault\n\n"
    "📈 Treiber: Europa verdoppelt die Ausgaben seit 2019, Kurs auf ~800 Mrd € bis 2030.\n"
    "⚖️ Rheinmetall: +15 % in einer Woche, aber −31 % seit Jahresstart — Boom trifft Vola.\n\n"
    "Rüstung ins Depot — ja oder nein? 👇\n\n"
    "⚠️ Keine Anlageberatung — nur Bildung & Unterhaltung. Kein Kauf-/Verkaufsaufruf.\n"
    "#rüstung #rheinmetall #verteidigung #aktien #börse #nato #investieren"
)


async def _main() -> None:
    opener = _ensure_clip(_OPENER_ID)
    cta = _ensure_clip(_CTA_ID)
    frames = [frame_powers(), frame_driver(), frame_valuation(), frame_stakes()]
    broll_paths = [opener, frames[0], frames[1], frames[2], frames[3], cta]

    segments = [ScriptSegment(text=t, broll_query="") for t in _TEXTS]
    script = ReelScript(hook=_TEXTS[0], segments=segments, caption=_CAPTION,
                        hashtags=[], title=_TITLE)

    with session_scope() as s:
        reel = ReelRow(trend_id=0, script_json=json.dumps({"title": _TITLE,
                       "topic": "ruestungsindustrie", "texts": _TEXTS}, ensure_ascii=False),
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
    print(f"Rüstungs-Reel #{rid} fertig: {video}")

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
