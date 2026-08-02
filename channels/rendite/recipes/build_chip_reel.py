"""Custom comparison REEL: the global chip industry — biggest players by country,
their segments, the rivalries, yesterday's chip selloff, and a valuation comparison.
Bright colorful opener + CTA (Pexels), four branded comparison frames, fluent
hand-written voiceover with livelier voice settings. Educational only.
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

# ── livelier, natural voice (process-local) ─────────────────────────────────
config.ELEVENLABS_STABILITY = 0.40
config.ELEVENLABS_STYLE = 0.40
config.ELEVENLABS_SPEED = 1.06

_OPENER_ID = int(os.getenv("OPENER_ID", "34336248"))  # warm colorful flowing waves
_CTA_ID = int(os.getenv("CTA_ID", "9668305"))         # bright colorful paint

W, H = 1080, 1920
F = branding.load_font
BG, CARD, BLUE, BLUEL, FG, MUTED = (branding.BG, branding.CARD, branding.BLUE,
                                    branding.BLUE_LIGHT, branding.FG, branding.MUTED)
RED, GREEN = branding.RED, branding.GREEN


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


# Instagram overlays the top of a reel with the profile name/menu, so keep the top
# ~290px empty. Subtitles sit low (MarginV 500 → ~y1260-1420), so content must fit
# inside the safe band y≈290–1250.
TOP = 290


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


def _save(img, name) -> str:
    out = Path(config.OUTPUT_DIR) / name
    img.save(out, quality=92)
    return str(out)


def frame_powers() -> str:
    img, d = _canvas()
    _kicker(d, "DIE CHIP-WELTMÄCHTE")
    _title(d, "Kein Land kann es allein")
    rows = [("USA", "Chip-Design", "Nvidia · AMD · Broadcom · Qualcomm"),
            ("Taiwan", "Fertigung", "TSMC — die Chip-Fabrik der Welt"),
            ("Niederlande", "Maschinen (EUV)", "ASML — konkurrenzlos"),
            ("Südkorea", "Speicher", "Samsung · SK Hynix"),
            ("Japan", "Ausrüstung", "Tokyo Electron · Advantest")]
    y, ch, gap = 476, 134, 14
    for country, role, comps in rows:
        d.rounded_rectangle((60, y, W - 60, y + ch), radius=22, fill=CARD)
        d.text((92, y + 20), country, font=F(42, bold=True), fill=FG)
        _rtext(d, W - 92, y + 28, role, F(28, bold=True), BLUEL)
        d.text((92, y + 80), comps, font=F(29), fill=MUTED)
        y += ch + gap
    _footer(d)
    return _save(img, "chip_frame_powers.jpg")


def frame_rivals() -> str:
    img, d = _canvas()
    _kicker(d, "DIE GROSSEN RIVALEN")
    _title(d, "Wer kämpft gegen wen?")
    duels = [("Nvidia", "AMD", "KI-Chips & Grafikkarten"),
             ("TSMC", "Samsung", "Chip-Fertigung"),
             ("ASML", "", "konkurrenzlos — das EUV-Monopol")]
    y, ch, gap = 478, 224, 24
    for a, b, seg in duels:
        d.rounded_rectangle((60, y, W - 60, y + ch), radius=22, fill=CARD)
        if b:
            _ctext(d, 300, y + 56, a, F(48, bold=True), BLUEL)
            _ctext(d, W / 2, y + 62, "vs", F(36, bold=True), MUTED)
            _ctext(d, W - 300, y + 56, b, F(48, bold=True), FG)
        else:
            _ctext(d, W / 2, y + 56, a, F(56, bold=True), BLUEL)
        _ctext(d, W / 2, y + 150, seg, F(31), MUTED)
        y += ch + gap
    _footer(d)
    return _save(img, "chip_frame_rivals.jpg")


def frame_crash() -> str:
    img, d = _canvas()
    _kicker(d, "GESTERN: DER CHIP-CRASH", RED)
    _title(d, "Rot auf breiter Front", color=RED)
    rows = [("AMD", "−8,3 %"), ("Nvidia", "−4,9 %"),
            ("Intel", "−3,5 %"), ("Chip-ETF (SMH)", "−4,1 %")]
    y, ch, gap = 476, 120, 14
    for name, pct in rows:
        d.rounded_rectangle((60, y, W - 60, y + ch), radius=20, fill=CARD)
        d.text((92, y + 34), name, font=F(42, bold=True), fill=FG)
        _rtext(d, W - 92, y + 30, pct, F(50, bold=True), RED)
        y += ch + gap
    y += 10
    d.rounded_rectangle((60, y, W - 60, y + 190), radius=20, fill=(34, 24, 28))
    d.text((92, y + 22), "Auslöser", font=F(30, bold=True), fill=RED)
    branding.wrap(d, "Bericht über einen China-Durchbruch bei der Chip-Technik "
                     "plus wachsende Sorge um die Finanzierung des KI-Booms.",
                  F(32), 92, y + 72, 42, FG, 44)
    _footer(d)
    return _save(img, "chip_frame_crash.jpg")


def frame_valuation() -> str:
    img, d = _canvas()
    _kicker(d, "BEWERTUNG IM VERGLEICH")
    _title(d, "Wer ist wie viel wert?")
    rows = [("Nvidia", "USA", "4,8 Bio. $"), ("TSMC", "Taiwan", "2,0 Bio. $"),
            ("Broadcom", "USA", "1,9 Bio. $"), ("Samsung", "Südkorea", "1,0 Bio. $"),
            ("ASML", "Niederlande", "0,6 Bio. $"), ("AMD", "USA", "0,45 Bio. $")]
    y, ch, gap = 472, 100, 10
    for name, land, val in rows:
        d.rounded_rectangle((60, y, W - 60, y + ch), radius=18, fill=CARD)
        d.text((90, y + 28), name, font=F(38, bold=True), fill=FG)
        d.text((410, y + 34), land, font=F(28), fill=MUTED)
        _rtext(d, W - 90, y + 28, val, F(40, bold=True), BLUEL)
        y += ch + gap
    y += 6
    branding.wrap(d, "Nvidia allein wiegt schwerer als fast alle Rivalen zusammen — "
                     "viel Fantasie, wenig Sicherheitspuffer.",
                  F(31), 90, y, 44, MUTED, 42)
    _footer(d)
    return _save(img, "chip_frame_valuation.jpg")


_TEXTS = [
    "Gestern sind die Chip-Aktien reihenweise abgestürzt. Höchste Zeit zu verstehen, "
    "wer dieses Business eigentlich beherrscht, das unsere ganze Welt antreibt.",
    "Kein Land schafft es allein. Die USA entwerfen die Chips, Taiwan baut sie, die "
    "Niederlande liefern als Einzige die Maschinen dafür, und Korea und Japan bringen "
    "Speicher und Technik.",
    "Die Rivalitäten sind gnadenlos. Nvidia gegen AMD bei den KI-Chips, TSMC gegen "
    "Samsung in der Fertigung. Nur ASML hat gar keine Konkurrenz, ein echtes Monopol.",
    "Und genau da traf es gestern. AMD stürzte über acht Prozent ab, Nvidia fast fünf. "
    "Auslöser waren ein möglicher China-Durchbruch und Sorge um die Finanzierung des KI-Booms.",
    "Im Vergleich sieht man, wie extrem die Bewertungen sind. Nvidia ist fast fünf "
    "Billionen Dollar wert, allein mehr als die meisten Rivalen zusammen.",
    "Auf welchen Chip-Giganten würdest du setzen? Schreib es in die Kommentare und folge "
    "für den echten Durchblick an der Börse!",
]

_CAPTION = (
    "🌍 Die Chip-Weltmacht erklärt — und warum sie gestern abstürzte.\n\n"
    "Gestern krachten die Chip-Aktien: AMD −8 %, Nvidia −5 %, der Chip-ETF SMH −4 %. "
    "Auslöser: ein gemeldeter China-Durchbruch bei der Fertigungstechnik + Sorge um die "
    "Finanzierung des KI-Booms.\n\n"
    "Wer beherrscht das wichtigste Business der Welt?\n"
    "🇺🇸 USA – Design (Nvidia, AMD, Broadcom)\n"
    "🇹🇼 Taiwan – Fertigung (TSMC)\n"
    "🇳🇱 Niederlande – Maschinen (ASML, EUV-Monopol)\n"
    "🇰🇷 Südkorea – Speicher (Samsung, SK Hynix)\n"
    "🇯🇵 Japan – Ausrüstung (Tokyo Electron)\n\n"
    "Auf welchen Giganten würdest du setzen? 👇\n\n"
    "⚠️ Keine Anlageberatung — nur Bildung & Unterhaltung. Kein Kauf-/Verkaufsaufruf.\n"
    "#chipaktien #halbleiter #nvidia #tsmc #asml #amd #börse #aktien #ki #investieren"
)


async def _main() -> None:
    opener = _ensure_clip(_OPENER_ID)
    cta = _ensure_clip(_CTA_ID)
    frames = [frame_powers(), frame_rivals(), frame_crash(), frame_valuation()]
    broll_paths = [opener, frames[0], frames[1], frames[2], frames[3], cta]

    segments = [ScriptSegment(text=t, broll_query="") for t in _TEXTS]
    script = ReelScript(hook=_TEXTS[0], segments=segments, caption=_CAPTION,
                        hashtags=[], title="Chip-Weltmächte — Vergleichs-Reel")

    with session_scope() as s:
        reel = ReelRow(trend_id=0, script_json=json.dumps({"topic": "chip industry",
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
    print(f"Chip-Reel #{rid} fertig: {video}")

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
