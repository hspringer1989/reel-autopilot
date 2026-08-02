"""MEME-Reel (neues Format C): kurzes, augenzwinkerndes "Niemand: — Leopold Aschenbrenner:"
Reel zum Fonds-Absturz. KEIN Voiceover, keine Analyse — nur Textkarten auf einem Sprungturm-
Clip, der die Dramaturgie liefert (oben stehen → Fall → Einschlag → Wasser wieder glatt).

Clip 9618065 (Pexels), Timing am echten Video vermessen:
  bis ~4,5 s  steht sie oben auf dem 10-Meter-Turm
  ~5,0 s      im Fall
  ~5,5 s      Einschlag mit Gischt
  ab ~7 s     Wasser beruhigt sich, Turm leer

Satire über ein öffentlich berichtetes Marktereignis (CNBC/FT/Handelsblatt), kein
persönlicher Angriff: der Spott gilt dem Hebel, nicht der Person. Disclaimer im Bild.
"""
import asyncio
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import httpx
from PIL import Image, ImageDraw

import config
from src import branding
from src.render.broll import _pick_file
from src.render.renderer import pick_music
from src.storage.database import ReelRow, session_scope

CLIP_ID = int(os.getenv("CLIP_ID", "9618065"))
W, H = 1080, 1920
DUR = 13.0
F = branding.load_font
FG = (255, 255, 255)

# Einblendungen, am Video ausgemessen
T_SETUP = (0.0, 4.7)      # sie steht oben
T_IMPACT = (5.45, 8.6)    # Einschlag + Nachwirkung
T_FACTS = (8.8, DUR)      # Wasser glatt, Turm leer


def _ensure_clip(vid: int) -> Path:
    cache = Path(config.BROLL_CACHE_DIR)
    for p in cache.glob(f"pexels_{vid}_*.mp4"):
        return p
    r = httpx.get(f"https://api.pexels.com/videos/videos/{vid}",
                  headers={"Authorization": config.PEXELS_API_KEY}, timeout=30)
    r.raise_for_status()
    fl = _pick_file(r.json())
    target = cache / f"pexels_{vid}_{fl['height']}.mp4"
    if not target.exists():
        data = httpx.get(fl["link"], timeout=180, follow_redirects=True)
        data.raise_for_status()
        cache.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data.content)
    return target


def _outline(d, xy, text, font, fill=FG, ow=6):
    """Meme-Text: weiß mit kräftiger schwarzer Kontur (auf jedem Untergrund lesbar)."""
    x, y = xy
    for dx in range(-ow, ow + 1, 2):
        for dy in range(-ow, ow + 1, 2):
            if dx or dy:
                d.text((x + dx, y + dy), text, font=font, fill=(0, 0, 0))
    d.text((x, y), text, font=font, fill=fill)


def _centered(d, y, text, size, fill=FG, ow=6):
    f = F(size, bold=True)
    w = d.textlength(text, font=f)
    _outline(d, ((W - w) / 2, y), text, f, fill, ow)
    return y + size + 14


def _overlay_setup() -> Path:
    """Meme-Aufbau: 'Niemand: ... Leopold Aschenbrenner:'"""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # dezenter Abdunkler hinter dem Text, damit er auf dem hellen Bad lesbar bleibt
    d.rounded_rectangle((50, 300, W - 50, 830), radius=28, fill=(0, 0, 0, 120))
    y = 330
    y = _centered(d, y, "Niemand:", 62)
    y = _centered(d, y + 6, "Absolut niemand:", 62)
    y += 30
    y = _centered(d, y, "Leopold Aschenbrenner,", 54, (255, 214, 10))
    y = _centered(d, y + 2, "25, mit 4-fachem Hebel", 54, (255, 214, 10))
    y = _centered(d, y + 2, "auf KI-Chips:", 54, (255, 214, 10))
    img.save("/tmp/ov_setup.png")
    return Path("/tmp/ov_setup.png")


def _overlay_impact() -> Path:
    """Der Einschlag."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    _centered(d, 470, "MARGIN CALL", 108, (255, 59, 48), ow=8)
    _centered(d, 610, "30. / 31. Juli 2026", 46)
    img.save("/tmp/ov_impact.png")
    return Path("/tmp/ov_impact.png")


def _overlay_facts() -> Path:
    """Die Fakten — kurz, damit das Meme trotzdem etwas hängen lässt."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((50, 330, W - 50, 900), radius=28, fill=(0, 0, 0, 130))
    y = 366
    y = _centered(d, y, "Vorher:  +439 %", 60, (52, 199, 89))
    y = _centered(d, y + 10, "Nachher:", 60)
    y = _centered(d, y + 4, "45 Mrd. $  →  10 Mrd. $", 58, (255, 59, 48))
    y += 24
    y = _centered(d, y, "in zwei Tagen.", 52)
    y += 18
    _centered(d, y, "Hebel vervierfacht auch Verluste.", 38, (200, 210, 225), ow=4)
    _centered(d, 1150, "Keine Anlageberatung · nur Bildung & Unterhaltung", 26,
              (190, 200, 215), ow=3)
    img.save("/tmp/ov_facts.png")
    return Path("/tmp/ov_facts.png")


_TITLE = "Niemand: — Leopold Aschenbrenner mit 4× Hebel:"

_CAPTION = (
    "Niemand: 🤐\n"
    "Absolut niemand:\n\n"
    "Leopold Aschenbrenner, 25, mit 4-fachem Hebel auf KI-Chips: 🤿💥\n\n"
    "Kurz zur Einordnung, weil die Geschichte wirklich so passiert ist:\n"
    "📈 +439 % netto bis zum 30. Juni 2026 — der bestlaufende große Fonds der Welt\n"
    "💸 Rund 45 Mrd. $ schwer, Hebel bis zum 4-Fachen auf Speicher- & Rechenzentrums-Aktien\n"
    "💥 Am 30./31. Juli: Margin Calls von Goldman Sachs, JPMorgan & BofA → das gesamte "
    "Aktienbuch ging mit Abschlag an Citadel\n"
    "📉 Übrig: rund 10 Mrd. $\n\n"
    "Das Bittere daran: Mit seiner These lag er richtig — KI braucht wirklich Chips und "
    "Rechenzentren. Nur zählt beim Hebel nicht, ob du am Ende recht hast, sondern ob du bis "
    "dahin durchhältst. 🪂\n\n"
    "⚠️ Keine Anlageberatung — nur Bildung & Unterhaltung. Kein Kauf-/Verkaufsaufruf.\n"
    "Quellen: CNBC, Financial Times, Handelsblatt (31.07./01.08.2026)\n"
    "#börsenmemes #hedgefonds #hebel #margincall #ki #aktien #börse #finanzhumor "
    "#investieren #finanzwissen"
)


async def _main() -> None:
    clip = _ensure_clip(CLIP_ID)
    ov1, ov2, ov3 = _overlay_setup(), _overlay_impact(), _overlay_facts()
    music = pick_music()

    with session_scope() as s:
        reel = ReelRow(trend_id=0,
                       script_json=json.dumps({"topic": "aschenbrenner meme",
                                               "title": _TITLE, "format": "meme"},
                                              ensure_ascii=False),
                       caption=_CAPTION, status="draft")
        s.add(reel); s.flush(); rid = reel.id

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out = Path(config.OUTPUT_DIR) / f"reel_{rid}_{stamp}.mp4"

    fc = (
        f"[0:v]scale={W}:-2,crop={W}:{H},trim=0:{DUR},setpts=PTS-STARTPTS[base];"
        f"[base][1:v]overlay=0:0:enable='between(t,{T_SETUP[0]},{T_SETUP[1]})'[v1];"
        f"[v1][2:v]overlay=0:0:enable='between(t,{T_IMPACT[0]},{T_IMPACT[1]})'[v2];"
        f"[v2][3:v]overlay=0:0:enable='between(t,{T_FACTS[0]},{T_FACTS[1]})'[vout]"
    )
    cmd = [config.FFMPEG_BIN, "-y", "-loglevel", "error",
           "-i", str(clip), "-i", str(ov1), "-i", str(ov2), "-i", str(ov3)]
    if music:
        # Musikbett, falls assets/music/ bestückt ist
        fc += (f";[4:a]atrim=0:{DUR},asetpts=PTS-STARTPTS,volume=-8dB,"
               f"afade=t=out:st={DUR-1.5}:d=1.5[aout]")
        cmd += ["-i", str(music)]
    cmd += ["-filter_complex", fc, "-map", "[vout]"]
    cmd += ["-map", "[aout]", "-c:a", "aac", "-b:a", "128k"] if music else ["-an"]
    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
            "-r", "25", "-shortest", str(out)]
    subprocess.run(cmd, check=True)
    if not music:
        print("HINWEIS: keine Musik in assets/music/ — Reel ist STUMM.")

    with session_scope() as s:
        r = s.get(ReelRow, rid)
        r.video_path = str(out)
        r.status = "pending_review"
    print(f"Meme-Reel #{rid} fertig: {out}")


if __name__ == "__main__":
    asyncio.run(_main())
