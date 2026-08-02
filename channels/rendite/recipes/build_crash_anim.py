"""MEME-Reel (Format C), komplett selbst animiert — kein Stockvideo.

Pexels hat kein brauchbares Kollaps-Material (geprüft 01.08.2026: "Sprengung" = Bagger
auf Trümmern, "Lawine" = statische Schneelandschaft, "Kartenhaus" = Seniorenrunde).
Deshalb wird der Absturz hier Frame für Frame gerendert: eine Kurve schießt auf +439 %,
bricht dann senkrecht ein — mit Zähler, Bildwackeln und rotem Einschlag.

Ablauf (25 fps, 15 s):
  0.0–2.2 s   Meme-Setup "Niemand: … Leopold Aschenbrenner mit 4× Hebel:"
  2.2–6.0 s   Kurve klettert, Zähler läuft 225 Mio → 45 Mrd. $
  6.0–7.0 s   Peak, +439 % pulsiert
  7.0–8.6 s   SENKRECHTER Absturz + Shake + "MARGIN CALL"
  8.6–15.0 s  Endkarte mit den Fakten

Satire über ein öffentlich berichtetes Marktereignis; der Spott gilt dem Hebel,
nicht der Person. Disclaimer im Bild.
"""
import asyncio
import json
import math
import random
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw

import config
from src import branding
from src.storage.database import ReelRow, session_scope

W, H = 1080, 1920
FPS = 25
DUR = 16.0
NF = int(DUR * FPS)
F = branding.load_font
BG = branding.BG
GREEN, RED, WHITE = (52, 199, 89), (255, 59, 48), (255, 255, 255)
MUTED = branding.MUTED
GOLD = (255, 214, 10)

FRAMES = Path("/tmp/anim")

# Chart-Fläche (füllt das Safe-Band y≈290–1250 aus, sonst wirkt das Bild leer)
CX0, CX1 = 80, W - 80
CY_TOP, CY_BOT = 600, 1240

# Zeitmarken in Frames — Absturz bewusst brutal kurz (0,9 s)
F_NEWS_END = int(2.0 * FPS)      # 50  Schlagzeilen-Karte (eigenes Layout + Quelle)
F_SETUP_END = int(4.0 * FPS)     # 100
F_RISE_END = int(7.4 * FPS)      # 185
F_PEAK_END = int(8.2 * FPS)      # 205
F_CRASH_END = int(9.1 * FPS)     # 227
F_CARD = int(9.5 * FPS)          # 237

N_RISE, N_CRASH, N_TAIL = 200, 40, 30
START_V, PEAK_V, END_V = 0.225, 45.0, 10.0   # Mrd. $


def _curve() -> list[tuple[float, float]]:
    """Normierte Punkte (x 0..1, v 0..1) — Anstieg, Einbruch, Auslauf."""
    pts = []
    for i in range(N_RISE):
        t = i / (N_RISE - 1)
        # exponentiell: lange flach, dann steil -> macht den Peak spektakulär
        v = 0.02 + 0.98 * (t ** 2.6)
        wobble = 0.012 * math.sin(t * 26) * (0.3 + t)
        pts.append((t * 0.66, max(0.0, v + wobble)))
    for i in range(N_CRASH):
        t = (i + 1) / N_CRASH
        v = 1.0 - 0.78 * (t ** 0.55)          # fast senkrecht nach unten
        pts.append((0.66 + t * 0.10, v))
    for i in range(N_TAIL):
        t = (i + 1) / N_TAIL
        pts.append((0.76 + t * 0.24, 0.22 + 0.006 * math.sin(t * 18)))
    return pts


CURVE = _curve()


def _idx(f: int) -> int:
    """Wie viele Kurvenpunkte sind in Frame f gezeichnet?"""
    if f < F_SETUP_END:
        return 0
    if f < F_RISE_END:
        return int(N_RISE * (f - F_SETUP_END) / (F_RISE_END - F_SETUP_END))
    if f < F_PEAK_END:
        return N_RISE
    if f < F_CRASH_END:
        k = (f - F_PEAK_END) / (F_CRASH_END - F_PEAK_END)
        return N_RISE + int(N_CRASH * k)
    k = min(1.0, (f - F_CRASH_END) / max(1, NF - F_CRASH_END))
    return N_RISE + N_CRASH + int(N_TAIL * k)


def _val(i: int) -> float:
    """Depotwert in Mrd. $ am Kurvenpunkt i."""
    if i <= 0:
        return START_V
    v = CURVE[min(i, len(CURVE) - 1)][1]
    return START_V + (PEAK_V - START_V) * v if v >= 0.22 else END_V


def _px(p: tuple[float, float]) -> tuple[float, float]:
    x, v = p
    return CX0 + x * (CX1 - CX0), CY_BOT - v * (CY_BOT - CY_TOP)


def _outline(d, xy, text, font, fill=WHITE, ow=5):
    x, y = xy
    for dx in range(-ow, ow + 1, 2):
        for dy in range(-ow, ow + 1, 2):
            if dx or dy:
                d.text((x + dx, y + dy), text, font=font, fill=(0, 0, 0))
    d.text((x, y), text, font=font, fill=fill)


def _ctr(d, y, text, size, fill=WHITE, ow=5, bold=True):
    f = F(size, bold=bold)
    w = d.textlength(text, font=f)
    _outline(d, ((W - w) / 2, y), text, f, fill, ow)
    return y + size + 12


def _fmt(v: float) -> str:
    return f"{v:.1f}".replace(".", ",") + " Mrd. $"


def _draw(f: int) -> Image.Image:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    i = _idx(f)
    crashing = F_PEAK_END <= f < F_CRASH_END
    after = f >= F_CRASH_END

    # Bildwackeln beim Einschlag
    sx = sy = 0
    if crashing:
        amp = 26 * (1 - (f - F_PEAK_END) / (F_CRASH_END - F_PEAK_END))
        sx, sy = random.randint(-int(amp), int(amp)), random.randint(-int(amp), int(amp))
        # roter Blitz in den ersten Frames des Absturzes
        if f - F_PEAK_END < 4:
            d.rectangle((0, 0, W, H), fill=(90, 18, 22))

    # Schlagzeilen-Karte: eigenes Layout, Quelle genannt — kein fremdes Bild,
    # kein nachgeahmtes Sender-Design.
    if f < F_NEWS_END:
        d.rounded_rectangle((60, 470, W - 60, 1030), radius=30, fill=(12, 24, 44),
                            outline=(70, 92, 124), width=3)
        kf = F(32, bold=True)
        kw = d.textlength("SO IST ES PASSIERT", font=kf)
        d.rounded_rectangle((100, 508, 100 + kw + 44, 508 + 58), radius=14, fill=RED)
        d.text((122, 519), "SO IST ES PASSIERT", font=kf, fill=WHITE)
        y = _ctr(d, 604, "KI-Hedgefonds", 76)
        y = _ctr(d, y - 4, "kollabiert", 76)
        y += 24
        _ctr(d, y, "Aschenbrenner verkauft sein", 38, (200, 212, 228), ow=3)
        _ctr(d, y + 52, "komplettes Aktienbuch an Citadel", 38, (200, 212, 228), ow=3)
        _ctr(d, y + 132, "CNBC · Financial Times · 31. Juli 2026", 30, MUTED, ow=3)

    # Meme-Setup
    if F_NEWS_END <= f < F_SETUP_END + 12:
        y = _ctr(d, 360 + sy, "Niemand:", 64)
        y = _ctr(d, y + 4, "Absolut niemand:", 64)
        y += 26
        y = _ctr(d, y, "Leopold Aschenbrenner, 25,", 50, GOLD)
        _ctr(d, y + 2, "mit 4-fachem Hebel:", 50, GOLD)

    if i > 0:
        col = RED if (crashing or after) else GREEN
        # Zähler + Rendite
        val = _val(i)
        _ctr(d, 320 + sy, _fmt(val), 98, col, ow=6)
        if not crashing and not after:
            pct = int(439 * min(1.0, i / N_RISE))
            _ctr(d, 452 + sy, f"+{pct} %", 60, GREEN)
        else:
            # laufend vom Peak aus gerechnet, damit Zahl und Prozent zusammenpassen
            _ctr(d, 452 + sy, f"−{int(round((1 - val / PEAK_V) * 100))} %", 60, RED)

        # Chart
        pts = [(_px(p)[0] + sx, _px(p)[1] + sy) for p in CURVE[:max(2, i)]]
        if len(pts) >= 2:
            base = CY_BOT + sy
            d.polygon(pts + [(pts[-1][0], base), (pts[0][0], base)],
                      fill=(20, 46, 32) if col is GREEN else (52, 20, 24))
            d.line(pts, fill=col, width=9, joint="curve")
            hx, hy = pts[-1]
            d.ellipse((hx - 13, hy - 13, hx + 13, hy + 13), fill=col)
        d.line((CX0 + sx, CY_BOT + sy, CX1 + sx, CY_BOT + sy), fill=(60, 76, 100), width=3)

    # Einschlag-Wort
    if crashing and f - F_PEAK_END > 3:
        _ctr(d, 700 + sy, "MARGIN CALL", 112, RED, ow=9)

    # Endkarte — halbtransparent, damit die eingebrochene Kurve sichtbar bleibt
    if f >= F_CARD:
        panel = Image.new("RGBA", (W - 120, 330), (6, 12, 24, 232))
        img.paste(Image.alpha_composite(
            img.crop((60, 620, W - 60, 950)).convert("RGBA"), panel).convert("RGB"), (60, 620))
        d.rounded_rectangle((60, 620, W - 60, 950), radius=28, outline=(70, 90, 120), width=3)
        y = _ctr(d, 652, "45 Mrd. $  →  10 Mrd. $", 62, RED)
        y = _ctr(d, y + 6, "in zwei Tagen.", 56)
        y += 12
        _ctr(d, y, "Er lag mit seiner These richtig.", 38, (200, 210, 225), ow=3)
        _ctr(d, y + 50, "Der Hebel war das Problem.", 38, (200, 210, 225), ow=3)
        # unter der Chart-Grundlinie, damit nichts auf der Kurve klebt
        _ctr(d, 1290, "Keine Anlageberatung · nur Bildung & Unterhaltung", 26,
             (170, 182, 200), ow=3)

    return img


_TITLE = "Niemand: — Leopold Aschenbrenner mit 4× Hebel:"

_CAPTION = (
    "Niemand: 🤐\n"
    "Absolut niemand:\n\n"
    "Leopold Aschenbrenner, 25, mit 4-fachem Hebel auf KI-Chips: 📉💥\n\n"
    "Und das ist keine erfundene Geschichte:\n"
    "📈 +439 % netto bis 30. Juni 2026 — der bestlaufende große Fonds der Welt\n"
    "💸 rund 45 Mrd. $ schwer, Hebel bis zum 4-Fachen auf Speicher- und "
    "Rechenzentrums-Aktien\n"
    "💥 30./31. Juli: Margin Calls von Goldman Sachs, JPMorgan und BofA → das komplette "
    "Aktienbuch ging mit Abschlag an Citadel\n"
    "📉 übrig: rund 10 Mrd. $\n\n"
    "Das Bittere: Mit seiner These lag er richtig — KI braucht wirklich Chips und "
    "Rechenzentren. Nur zählt beim Hebel nicht, ob du am Ende recht hast, sondern ob du "
    "bis dahin durchhältst.\n\n"
    "⚠️ Keine Anlageberatung — nur Bildung & Unterhaltung. Kein Kauf-/Verkaufsaufruf.\n"
    "Quellen: CNBC, Financial Times, Handelsblatt (31.07./01.08.2026)\n"
    "#börsenmemes #hedgefonds #hebel #margincall #ki #aktien #börse #finanzhumor "
    "#investieren #finanzwissen"
)


async def _main() -> None:
    random.seed(7)
    if FRAMES.exists():
        shutil.rmtree(FRAMES)
    FRAMES.mkdir(parents=True)
    for f in range(NF):
        _draw(f).save(FRAMES / f"f_{f:05d}.jpg", quality=92)
    print(f"{NF} Frames gerendert")

    with session_scope() as s:
        reel = ReelRow(trend_id=0,
                       script_json=json.dumps({"topic": "aschenbrenner crash meme",
                                               "title": _TITLE, "format": "meme-anim"},
                                              ensure_ascii=False),
                       caption=_CAPTION, status="draft")
        s.add(reel); s.flush(); rid = reel.id

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out = Path(config.OUTPUT_DIR) / f"reel_{rid}_{stamp}.mp4"
    subprocess.run([config.FFMPEG_BIN, "-y", "-loglevel", "error", "-framerate", str(FPS),
                    "-i", str(FRAMES / "f_%05d.jpg"), "-c:v", "libx264", "-preset", "medium",
                    "-crf", "20", "-pix_fmt", "yuv420p", "-an", str(out)], check=True)

    with session_scope() as s:
        r = s.get(ReelRow, rid)
        r.video_path = str(out)
        r.status = "pending_review"
    print(f"Crash-Meme #{rid} fertig: {out}")


if __name__ == "__main__":
    asyncio.run(_main())
