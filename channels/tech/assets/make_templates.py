"""Erzeugt die Bild-Templates des Kanals "Tech Kompakt" reproduzierbar aus der Palette.

Aufruf (aus dem Repo-Wurzelverzeichnis):
    venv/bin/python channels/tech/assets/make_templates.py

Erzeugt in channels/tech/assets/templates/:
    feed_bg_title.png    1080×1350  — Hintergrund ALLER Carousel-Slides
    feed_bg_content.png  1080×1350  — vom Renderer derzeit nicht genutzt, aber von
                                      tests/test_profiles.py::test_channel_assets_exist verlangt
    avatar.png           1080×1080  — Profilbild-Monogramm (BRAND_AVATAR in der .env)

Layout-Zwänge kommen aus src/feedposts/renderer.py und dürfen nicht verletzt werden:
  - Der Slide-Zähler wird bei (70, 66) in der Akzentfarbe auf das Template gezeichnet.
  - Ein dunkles Textpanel (Deckkraft ~210/255) liegt über x 50–1030, y 129–1175.
    Alles Dekorative dort ist im Ergebnis praktisch unsichtbar.
  → Die Wortmarke sitzt deshalb im unteren Streifen ab y≈1200, wo nichts sie überdeckt.

Dieses Skript importiert bewusst weder config noch src (es läuft eigenständig) und
liest die Palette aus der Profil-Datei nebenan.
"""
from __future__ import annotations

import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1080, 1350
HERE = Path(__file__).resolve().parent
OUT = HERE / "templates"

# Palette gespiegelt aus channels/tech/profile.py (bewusst dupliziert statt importiert,
# damit das Skript ohne Repo-Pfad-Gefummel läuft — bei Palettenwechsel hier mitziehen).
TURQUOISE = (45, 212, 191)
TURQUOISE_LIGHT = (127, 233, 220)
TURQUOISE_DEEP = (15, 118, 110)
BG = (24, 26, 30)
CARD = (32, 35, 40)
FG = (240, 243, 245)
MUTED = (154, 162, 170)

WORDMARK_1, WORDMARK_2 = "TECH", "KOMPAKT"

_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def font(size: int) -> ImageFont.FreeTypeFont:
    for path in _FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _base(width: int, height: int) -> Image.Image:
    """Anthrazit-Grund mit sanftem vertikalem Verlauf (oben minimal heller)."""
    img = Image.new("RGB", (width, height), BG)
    grad = Image.new("L", (1, height))
    for y in range(height):
        # 0 oben → 1 unten, oben etwas aufgehellt
        grad.putpixel((0, y), int(26 * (1 - y / height)))
    grad = grad.resize((width, height))
    lift = Image.new("RGB", (width, height), (54, 60, 68))
    return Image.composite(lift, img, grad)


def _glow(img: Image.Image, center: tuple[int, int], radius: int, color, strength: int) -> Image.Image:
    """Weicher radialer Schein — gibt der Fläche Tiefe, ohne Struktur zu erzwingen."""
    layer = Image.new("RGB", img.size, (0, 0, 0))
    mask = Image.new("L", img.size, 0)
    d = ImageDraw.Draw(mask)
    cx, cy = center
    d.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=strength)
    mask = mask.filter(ImageFilter.GaussianBlur(radius // 2))
    ImageDraw.Draw(layer).rectangle((0, 0, *img.size), fill=color)
    # bewusst schwach: der Grund soll anthrazit bleiben, das Türkis lebt in den Bahnen
    return Image.composite(Image.blend(img, layer, 0.34), img, mask)


def _dot_grid(draw: ImageDraw.ImageDraw, step: int, color, alpha: int, height: int) -> None:
    """Feines Punktraster — Platinen-/Terminal-Anmutung, sehr zurückhaltend."""
    rgba = color + (alpha,)
    for y in range(step, height, step):
        for x in range(step, W, step):
            draw.rectangle((x, y, x + 1, y + 1), fill=rgba)


def _trace(draw: ImageDraw.ImageDraw, start: tuple[int, int], rnd: random.Random,
           width: int, height: int, alpha: int, thickness: int) -> None:
    """Eine Leiterbahn: Schritte nur waagerecht, senkrecht oder 45° — so entsteht die
    typische Platinen-Geometrie statt einer beliebigen Zickzacklinie. Endet auf einem Pad."""
    x, y = start
    pts = [(x, y)]
    direction = rnd.choice([(1, 0), (0, 1), (0, -1), (1, 1), (1, -1)])
    for _ in range(rnd.randint(3, 6)):
        step = rnd.randint(90, 240)
        x += direction[0] * step
        y += direction[1] * step
        x = max(-60, min(width + 60, x))
        y = max(-60, min(height + 60, y))
        pts.append((x, y))
        # Richtungswechsel um 45° oder 90°, nie Kehrtwende
        direction = rnd.choice([d for d in [(1, 0), (0, 1), (0, -1), (1, 1), (1, -1)]
                                if d != (-direction[0], -direction[1])])

    draw.line(pts, fill=TURQUOISE + (alpha,), width=thickness, joint="curve")
    # Lötaugen an Anfang und Ende
    for px, py in (pts[0], pts[-1]):
        r = thickness + 4
        draw.ellipse((px - r, py - r, px + r, py + r), outline=TURQUOISE + (alpha + 60,),
                     width=max(2, thickness - 1))


def _circuit(draw: ImageDraw.ImageDraw, seed: int, width: int, height: int) -> None:
    """Vollflächiges Leiterbahn-Motiv — trägt das Bild auch dort, wo das Textpanel fehlt."""
    rnd = random.Random(seed)
    # hintere, ruhige Ebene
    for _ in range(14):
        _trace(draw, (rnd.randint(-40, width), rnd.randint(-40, height)), rnd,
               width, height, alpha=34, thickness=3)
    # vordere, hellere Akzentbahnen
    for _ in range(5):
        _trace(draw, (rnd.randint(-40, width), rnd.randint(-40, height)), rnd,
               width, height, alpha=96, thickness=4)


def _wordmark_bottom_left(img: Image.Image) -> None:
    """Wortmarke unten links — der einzige Bereich, den das Textpanel nie überdeckt."""
    draw = ImageDraw.Draw(img)
    f = font(46)
    y = 1252
    draw.rectangle((70, y - 26, 70 + 96, y - 20), fill=TURQUOISE)  # Akzentstrich darüber
    draw.text((70, y), f"{WORDMARK_1} {WORDMARK_2}", font=f, fill=FG)


def build_title() -> Path:
    img = _base(W, H)
    img = _glow(img, (430, 430), 660, TURQUOISE_DEEP, 140)
    img = _glow(img, (940, 1150), 420, TURQUOISE_DEEP, 80)

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    _dot_grid(d, 45, TURQUOISE, 24, H)
    _circuit(d, seed=11, width=W, height=H)
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

    _wordmark_bottom_left(img)
    out = OUT / "feed_bg_title.png"
    img.save(out, "PNG")
    return out


def build_content() -> Path:
    """Flachere, dunklere Variante. Der Renderer nutzt sie aktuell nicht (alle Slides
    ziehen FEED_TEMPLATE_TITLE), tests/test_profiles.py verlangt sie aber — und falls
    die Engine sie je wieder einsetzt, passt sie ins Bild."""
    img = _base(W, H)
    img = _glow(img, (760, 300), 460, TURQUOISE_DEEP, 54)

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    _dot_grid(d, 60, TURQUOISE, 12, H)

    # ruhige, leicht abgehobene Panels — Andeutung von Karten/Fenstern
    for box in ((80, 250, 380, 400), (620, 190, 1000, 320), (150, 470, 460, 600),
                (700, 560, 1010, 690)):
        d.rounded_rectangle(box, radius=18, fill=CARD + (150,))

    # Signal-/Datenlinie am unteren Rand
    pts = [(0, 1180), (150, 1130), (300, 1155), (450, 1080), (600, 1105),
           (760, 1035), (900, 1060), (1080, 1000)]
    d.line(pts, fill=TURQUOISE + (210,), width=8, joint="curve")
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

    # Wortmarke oben rechts (hier liegt kein Zähler)
    draw = ImageDraw.Draw(img)
    f = font(42)
    text = f"{WORDMARK_1} {WORDMARK_2}"
    tw = draw.textlength(text, font=f)
    draw.text((W - 70 - tw, 84), text, font=f, fill=FG)

    out = OUT / "feed_bg_content.png"
    img.save(out, "PNG")
    return out


def build_avatar() -> Path:
    """Quadratisches Profilbild; src/feedposts/photo.py schneidet es rund zu."""
    size = 1080
    img = _base(size, size)
    img = _glow(img, (size // 2, size // 2), 520, TURQUOISE_DEEP, 120)

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    _dot_grid(d, 54, TURQUOISE, 18, size)
    d.ellipse((90, 90, size - 90, size - 90), outline=TURQUOISE + (120,), width=6)
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

    draw = ImageDraw.Draw(img)

    def fit(text: str, start: int, max_width: int) -> ImageFont.FreeTypeFont:
        """Größte Schrift, mit der der Text in die sichere Breite passt — der Avatar wird
        von src/feedposts/photo.py rund zugeschnitten, Randnähe würde abgeschnitten."""
        f = font(start)
        while start > 40 and draw.textlength(text, font=f) > max_width:
            start -= 6
            f = font(start)
        return f

    safe = 620  # bequem innerhalb des Kreises (Radius 450 um die Mitte)
    f1 = fit(WORDMARK_1, 210, safe)
    f2 = fit(WORDMARK_2, 150, safe)
    for text, f, y, fill in ((WORDMARK_1, f1, 380, FG), (WORDMARK_2, f2, 585, TURQUOISE)):
        tw = draw.textlength(text, font=f)
        draw.text(((size - tw) / 2, y), text, font=f, fill=fill)

    out = OUT / "avatar.png"
    img.save(out, "PNG")
    return out


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for path in (build_title(), build_content(), build_avatar()):
        img = Image.open(path)
        print(f"{path.relative_to(HERE.parents[2])}  {img.size[0]}×{img.size[1]}")
