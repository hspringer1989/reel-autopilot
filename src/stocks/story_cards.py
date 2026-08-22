"""Renders 1080×1920 Instagram-story cards with Pillow. Story stickers/links are
NOT available via the Graph API, so every bit of text (incl. the disclaimer, the
traffic-light signal and the chart-derived risk marks) is baked into the image.

Per candidate we render THREE cards (one story, three frames):
  1) Charttechnik — with a drawn price chart + chart traffic light
  2) Fundamental  — key figures + fundamental traffic light
  3) Gesamtbild   — combined traffic light + recap
The traffic light (green/amber/red) is an OBSERVATIONAL read of the data
(bullish/neutral/bearish), never a buy/sell instruction (BaFin/MAR framing).

Pillow is imported lazily so the rest of the pipeline imports without it."""
from __future__ import annotations

import textwrap
from pathlib import Path

import config
from src import branding
from src.models import Candidate, EarningsItem
from src.stocks import indicators as ind

W, H = 1080, 1920
_TOP = 250          # start content below Instagram's profile-name overlay at the top
_MARGIN = 60        # left/right content margin (container spans 60 … W-60)
_BG = branding.BG
_FG = branding.FG
_MUTED = branding.MUTED
_CARD = branding.CARD
_BRAND = branding.BLUE       # brand accent (header, ticker, badges)
_ACCENT = branding.GREEN     # semantic "up/target/positive" (traffic light, TP line)
_AMBER = branding.AMBER
_RED = branding.RED
_BLUE = branding.BLUE_LIGHT  # SMA20 chart overlay
_LIGHT = branding.LIGHT
_font = branding.load_font
_market_badge = branding.market_badge


def _new_card():
    from PIL import Image, ImageDraw

    # No brand header at the top: Instagram overlays the profile name (@rendite.radar.official)
    # there in stories, so a baked-in header would collide with it.
    img = Image.new("RGB", (W, H), _BG)
    draw = ImageDraw.Draw(img)
    _footer(draw)
    return img, draw


def _footer(draw) -> None:
    disclaimer = config.PROFILE.CARD_FOOTER_DISCLAIMER
    draw.line((60, H - 150, W - 60, H - 150), fill=_MUTED, width=2)
    draw.text((60, H - 130), disclaimer, font=_font(26), fill=_MUTED)


def _wrap(draw, text: str, font, x: int, y: int, width_chars: int, fill, line_h: int) -> int:
    for para in text.split("\n"):
        for line in textwrap.wrap(para, width=width_chars) or [""]:
            draw.text((x, y), line, font=font, fill=fill)
            y += line_h
    return y


def _wrap_px(draw, text: str, font, x: int, y: int, right: int, fill, line_h: int,
             max_lines: int | None = None) -> int:
    """Wrap text to the FULL container width (x … right) by measuring pixels, so lines
    reach the right edge instead of breaking early (no ugly right-hand indent). With
    `max_lines`, extra text is trimmed and the last visible line ends with an ellipsis."""
    max_w = right - x
    lines: list[str] = []
    for para in text.split("\n"):
        line = ""
        for word in para.split():
            trial = f"{line} {word}".strip()
            if line and draw.textlength(trial, font=font) > max_w:
                lines.append(line)
                line = word
            else:
                line = trial
        if line:
            lines.append(line)
    if max_lines is not None and len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        while last and draw.textlength(last + " …", font=font) > max_w:
            last = last.rsplit(" ", 1)[0] if " " in last else last[:-1]
        lines[-1] = last + " …"
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        y += line_h
    return y


def _center(draw, text: str, font, y: int, fill) -> None:
    w = draw.textlength(text, font=font)
    draw.text(((W - w) / 2, y), text, font=font, fill=fill)


def _center_wrap(draw, text: str, font, y: int, width_chars: int, fill, line_h: int) -> int:
    for line in branding.wrap_lines(text, width_chars):
        w = draw.textlength(line, font=font)
        draw.text(((W - w) / 2, y), line, font=font, fill=fill)
        y += line_h
    return y


def render_new_post_story(title: str, out_path: str, badge: str = "NEUER BEITRAG",
                          sub: str = "gerade im Feed erschienen",
                          cta: str = "Jetzt im Feed ansehen") -> str:
    """A striking announcement story for fresh content (feed carousel or reel).

    Graph-API stories can't carry a tappable link/sticker, so instead of a fake button
    we point users to the ONE tappable element Instagram itself provides: the profile
    name at the top of the story (tapping it opens the profile → the new content)."""
    img, draw = _new_card()
    draw.rounded_rectangle((80, 470, W - 80, 668), radius=54, fill=_BRAND)
    _center(draw, badge, _font(84, bold=True), 512, (255, 255, 255))
    _center(draw, sub, _font(40), 760, _MUTED)

    # Title: shrink-to-fit + line cap inside the band between the sub-line and the CTA,
    # so an over-long title (e.g. a whole reel hook) can never overflow the card again.
    tx0, ty0, ty1 = 90, 820, 1220
    max_w = W - 2 * tx0
    font = _font(34, bold=True)
    lines = _wrap_lines_px(draw, title, font, max_w)
    lh = int(34 * 1.28)
    for size in range(62, 33, -2):
        f = _font(size, bold=True)
        ls = _wrap_lines_px(draw, title, f, max_w)
        h = int(size * 1.28)
        if len(ls) * h <= (ty1 - ty0):
            font, lines, lh = f, ls, h
            break
    lines = lines[: max(1, (ty1 - ty0) // lh)]
    yy = ty0 + ((ty1 - ty0) - len(lines) * lh) // 2   # vertically centered in the band
    for ln in lines:
        w = draw.textlength(ln, font=font)
        draw.text(((W - w) / 2, yy), ln, font=font, fill=_FG)
        yy += lh

    _center(draw, cta, _font(46, bold=True), 1280, _BRAND)
    _center(draw, "tippe oben auf mein Profil", _font(34), 1352, _MUTED)
    return _save(img, out_path)


def _save(img, out_path: str) -> str:
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "JPEG", quality=90)
    return out_path




def _signal_badge(draw, x: int, y: int, level: str, label: str, big: bool = False) -> None:
    """Traffic-light dot + label. level ∈ {'pos','neu','neg'}."""
    r = 26 if big else 20
    cy = y + (34 if big else 26)
    draw.ellipse((x, cy - r, x + 2 * r, cy + r), fill=_LIGHT.get(level, _MUTED))
    draw.text((x + 2 * r + 20, y + (20 if big else 14)),
              label, font=_font(44 if big else 34, bold=True), fill=_FG)


def _level_row(draw, y: int, label: str, value: str, color) -> None:
    draw.text((90, y), label, font=_font(30), fill=_MUTED)
    draw.text((560, y), value, font=_font(32, bold=True), fill=color)


# ── Chart drawing ──────────────────────────────────────────────────────────
def _draw_chart(draw, box, closes, stop, take, entry, currency) -> None:
    """Simple price line chart with SMA20/50 overlays and stop/target marks."""
    x0, y0, x1, y1 = box
    draw.rounded_rectangle(box, radius=20, fill=_CARD)
    pad = 30
    ax0, ay0, ax1, ay1 = x0 + pad, y0 + pad, x1 - pad, y1 - pad - 30

    if not closes or len(closes) < 2:
        draw.text((x0 + pad, y0 + pad), "Chartdaten nicht verfügbar", font=_font(30), fill=_MUTED)
        return

    lo = min(min(closes), stop)
    hi = max(max(closes), take)
    if hi <= lo:
        hi = lo + 1.0

    def X(i: int) -> float:
        return ax0 + (ax1 - ax0) * i / (len(closes) - 1)

    def Y(v: float) -> float:
        return ay1 - (ay1 - ay0) * (v - lo) / (hi - lo)

    # horizontal marks: target (green), stop (red), reference (muted)
    for val, col in ((take, _ACCENT), (stop, _RED), (entry, _MUTED)):
        yv = Y(val)
        draw.line((ax0, yv, ax1, yv), fill=col, width=2)
    draw.text((ax0 + 6, Y(take) - 30), f"Ziel {take:.0f} {currency}", font=_font(22), fill=_ACCENT)
    draw.text((ax0 + 6, Y(stop) + 6), f"Stop {stop:.0f} {currency}", font=_font(22), fill=_RED)

    # SMA overlays (drawn under the price line)
    for series, col in ((ind.sma_series(closes, 50), _MUTED), (ind.sma_series(closes, 20), _BLUE)):
        pts = [(X(i), Y(v)) for i, v in enumerate(series) if v is not None]
        if len(pts) > 1:
            draw.line(pts, fill=col, width=2)

    # price line on top
    draw.line([(X(i), Y(v)) for i, v in enumerate(closes)], fill=_FG, width=3)

    # legend
    ly = y1 - 24
    draw.text((ax0, ly), "— Kurs", font=_font(22), fill=_FG)
    draw.text((ax0 + 150, ly), "— 20-Tage", font=_font(22), fill=_BLUE)
    draw.text((ax0 + 330, ly), "— 50-Tage", font=_font(22), fill=_MUTED)


# ── Combined single analysis card (template "Story-Card-selection") ─────────
# Design: near-black page, two light cards (Fundamental figures + Charttechnik chart),
# a dark FAZIT strip with the overall traffic light. Everything on ONE story.
_PAGE = (10, 14, 22)          # near-black page background
_CARD_LT = (243, 241, 235)    # cream card
_TILE = (231, 229, 221)       # stat tile
_INK = (20, 26, 34)           # dark text on light card
_INK_MUT = (108, 118, 130)    # muted dark text
_CHIP = (24, 28, 36)          # dark number chip / fazit strip
_CHARTBG = (16, 22, 32)       # dark chart panel inside the light card


def _tint(color, amount: float = 0.82):
    """Light pastel tint of a signal colour (for the ZIEL/STOP value boxes)."""
    return tuple(int(c + (255 - c) * amount) for c in color)


def _ampel_pill(draw, right_x: int, y: int, level: str) -> None:
    """Dark rounded pill with three dots; the dot for `level` is lit in its signal colour."""
    w, h = 132, 54
    x = right_x - w
    draw.rounded_rectangle((x, y, x + w, y + h), radius=27, fill=_CHIP)
    colors = {"neg": _RED, "neu": _AMBER, "pos": _ACCENT}
    for i, lv in enumerate(("neg", "neu", "pos")):
        cx, cy = x + 30 + i * 36, y + h // 2
        col = colors[lv] if lv == level else (74, 82, 94)
        draw.ellipse((cx - 12, cy - 12, cx + 12, cy + 12), fill=col)


def _section_title(draw, x: int, y: int, num: str, title: str, level: str) -> None:
    s = 54
    draw.rounded_rectangle((x, y, x + s, y + s), radius=12, fill=_CHIP)
    # center the number in the chip via its real glyph box (fixes off-centre 01/02)
    nf = _font(30, bold=True)
    l, t, r, b = draw.textbbox((0, 0), num, font=nf)
    draw.text((x + (s - (r - l)) / 2 - l, y + (s - (b - t)) / 2 - t), num,
              font=nf, fill=(255, 255, 255))
    draw.text((x + 74, y + 6), title, font=_font(44, bold=True), fill=_INK)
    _ampel_pill(draw, W - 76, y, level)


def _stat_tile(draw, box, value: str, label: str) -> None:
    x0, y0, x1, _ = box
    draw.rounded_rectangle(box, radius=16, fill=_TILE)
    cx = (x0 + x1) // 2
    vf = _font(44, bold=True)
    draw.text((cx - draw.textlength(value, font=vf) / 2, y0 + 20), value, font=vf, fill=_INK)
    lf = _font(23)
    draw.text((cx - draw.textlength(label, font=lf) / 2, y0 + 80), label, font=lf, fill=_INK_MUT)


def _val_box(draw, x: int, y: int, label: str, value: str, color) -> None:
    w, h = 218, 122
    draw.rounded_rectangle((x, y, x + w, y + h), radius=16, fill=_tint(color))
    draw.text((x + 20, y + 16), label, font=_font(24, bold=True), fill=color)
    # auto-shrink the value so wide prices (e.g. '3837 GBp') never spill out of the box
    sz = 42
    for sz in range(42, 25, -2):
        if draw.textlength(value, font=_font(sz, bold=True)) <= w - 40:
            break
    draw.text((x + 20, y + 54 + (42 - sz) // 2), value, font=_font(sz, bold=True), fill=color)


def _dashed_hline(draw, x0: int, x1: int, y: float, color, dash: int = 16, gap: int = 12) -> None:
    x = x0
    while x < x1:
        draw.line((x, y, min(x + dash, x1), y), fill=color, width=3)
        x += dash + gap


def _mini_chart(draw, box, m, c) -> None:
    x0, y0, x1, y1 = box
    draw.rounded_rectangle(box, radius=18, fill=_CHARTBG)
    closes = m.history_closes
    if not closes or len(closes) < 2:
        draw.text((x0 + 24, y0 + 24), "Chartdaten n/a", font=_font(26), fill=_MUTED)
        return
    pad = 26
    ax0, ay0, ax1, ay1 = x0 + pad, y0 + pad + 6, x1 - pad, y1 - pad
    lo, hi = min(min(closes), c.stop_loss), max(max(closes), c.take_profit)
    import math
    if not all(math.isfinite(v) for v in (lo, hi, c.stop_loss, c.take_profit)):
        # defensive: a non-finite price/risk-mark must never crash the whole build
        draw.text((x0 + 24, y0 + 24), "Chartdaten n/a", font=_font(26), fill=_MUTED)
        return
    if hi <= lo:
        hi = lo + 1.0
    def X(i): return ax0 + (ax1 - ax0) * i / (len(closes) - 1)
    def Y(v): return ay1 - (ay1 - ay0) * (v - lo) / (hi - lo)
    _dashed_hline(draw, ax0, ax1, Y(c.take_profit), _ACCENT)
    _dashed_hline(draw, ax0, ax1, Y(c.stop_loss), _RED)
    draw.text((ax0 + 2, Y(c.take_profit) - 30), "ZIEL", font=_font(22, bold=True), fill=_ACCENT)
    draw.text((ax0 + 2, Y(c.stop_loss) + 6), "STOP", font=_font(22, bold=True), fill=_RED)
    pts = [(X(i), Y(v)) for i, v in enumerate(closes)]
    draw.line(pts, fill=_BRAND, width=5)
    ex, ey = pts[-1]
    draw.ellipse((ex - 9, ey - 9, ex + 9, ey + 9), fill=(255, 255, 255))


def _wrap_lines_px(draw, text: str, font, max_w: int) -> list[str]:
    out: list[str] = []
    for para in text.split("\n"):
        line = ""
        for word in para.split():
            trial = f"{line} {word}".strip()
            if line and draw.textlength(trial, font=font) > max_w:
                out.append(line)
                line = word
            else:
                line = trial
        if line:
            out.append(line)
    return out


def _draw_fit(draw, text: str, box, fill, size_max: int, size_min: int,
              bold: bool = False, ratio: float = 1.34) -> int:
    """Draw `text` wrapped inside `box` (x0,y0,x1,y1), shrinking the font from size_max
    down until ALL of it fits — so text is never cut off (no ellipsis)."""
    x0, y0, x1, y1 = box
    bw, bh = x1 - x0, y1 - y0
    font = _font(size_min, bold)
    lh = int(size_min * ratio)
    lines = _wrap_lines_px(draw, text, font, bw)
    for size in range(size_max, size_min - 1, -1):
        f = _font(size, bold)
        h = int(size * ratio)
        ls = _wrap_lines_px(draw, text, f, bw)
        if len(ls) * h <= bh:
            font, lh, lines = f, h, ls
            break
    else:
        lines = lines[: max(1, bh // lh)]  # pathological length only
    yy = y0
    for line in lines:
        draw.text((x0, yy), line, font=font, fill=fill)
        yy += lh
    return yy


_FAZIT_HEADING = {"pos": "Chancen überwiegen", "neu": "Ausgewogenes Bild", "neg": "Risiken überwiegen"}
_INK_SOFT = (66, 74, 86)      # dark body text on the light Fazit card
_HEAD_SUB = (224, 230, 238)   # near-white header subtitle (was grey)
_DOT_OFF_LT = (201, 205, 212)  # inactive traffic dot on a light background


def render_analysis_card(c: Candidate, out_path: str) -> str:
    """ONE story card with Fundamental + Charttechnik + Fazit (template design).
    Text boxes auto-shrink their font so nothing is ever cut off."""
    from PIL import Image, ImageDraw

    m = c.metrics
    img = Image.new("RGB", (W, H), _PAGE)
    draw = ImageDraw.Draw(img)
    y = _TOP

    # header: (trend badge) + ticker + name (subtitle in near-white, not grey)
    if c.category:
        w = draw.textlength(c.category, font=_font(26, bold=True))
        draw.rounded_rectangle((40, y, 40 + w + 40, y + 46), radius=12, fill=_BRAND)
        draw.text((60, y + 8), c.category, font=_font(26, bold=True), fill=(255, 255, 255))
        y += 60
    x = _market_badge(draw, 40, y + 10, m.market)
    name = _truncate_px(draw, _clean_name(m.name), _font(54, bold=True), W - x - 56)
    draw.text((x, y), name, font=_font(54, bold=True), fill=_FG)         # clean company name = heading
    tf = _font(26, bold=True)
    draw.text((x, y + 64), m.ticker, font=tf, fill=_BRAND)               # ticker small below
    draw.text((x + draw.textlength(m.ticker, font=tf), y + 64),
              f"  ·  {m.sector}", font=_font(26), fill=_HEAD_SUB)
    y += 122

    # ── Card 01 · Fundamental ────────────────────────────────────────────────
    f_lvl, _ = ind.tendency(m.fund_score, "fund")
    fh = 402
    draw.rounded_rectangle((40, y, W - 40, y + fh), radius=28, fill=_CARD_LT)
    _section_title(draw, 76, y + 30, "01", "Fundamental", f_lvl)
    tiles = [
        (_fig(m.pe), "KGV"),
        (f"{m.dividend_yield:.1f} %".replace(".", ",") if m.dividend_yield else "—", "Div.-Rendite"),
        (_fig(m.revenue_growth, pct=True), "Umsatz +"),
        (_fig(m.profit_margin, pct=True), "Marge"),
    ]
    tw, gap = 218, 14
    tx = 76
    for value, label in tiles:
        _stat_tile(draw, (tx, y + 108, tx + tw, y + 232), value, label)
        tx += tw + gap
    _draw_fit(draw, c.fundamental_text, (76, y + 250, W - 76, y + fh - 20), _INK, 32, 23)
    y += fh + 24

    # ── Card 02 · Charttechnik ───────────────────────────────────────────────
    c_lvl, _ = ind.tendency(m.tech_score, "chart")
    ch = 556
    draw.rounded_rectangle((40, y, W - 40, y + ch), radius=28, fill=_CARD_LT)
    _section_title(draw, 76, y + 30, "02", "Charttechnik", c_lvl)
    _mini_chart(draw, (76, y + 108, 748, y + 380), m, c)
    _val_box(draw, 782, y + 108, "ZIEL", f"{c.take_profit:.0f} {m.currency}", _ACCENT)
    _val_box(draw, 782, y + 258, "STOP", f"{c.stop_loss:.0f} {m.currency}", _RED)
    _draw_fit(draw, c.chart_text, (76, y + 398, W - 76, y + ch - 18), _INK, 32, 23)
    y += ch + 24

    # ── Fazit strip (light background, like the cards above) ─────────────────
    o_lvl, o_label = ind.tendency(m.blended, "overall")
    fzh = 300
    draw.rounded_rectangle((40, y, W - 40, y + fzh), radius=28, fill=_CARD_LT)
    draw.text((76, y + 40), "FAZIT", font=_font(26, bold=True), fill=_INK_MUT)
    for i, lv in enumerate(("neg", "neu", "pos")):
        cx = 76 + i * 46
        col = _LIGHT[lv] if lv == o_lvl else _DOT_OFF_LT
        draw.ellipse((cx, y + 92, cx + 32, y + 124), fill=col)
    draw.text((250, y + 36), f"Gesamtbild · {o_label}", font=_font(28, bold=True), fill=_INK_MUT)
    yy = _draw_fit(draw, _FAZIT_HEADING.get(o_lvl, "Ausgewogenes Bild"),
                   (250, y + 74, W - 76, y + 146), _INK, 46, 34, bold=True)
    body = f"Im Trend: {c.trend_reason}" if c.trend_reason else c.overall_text
    body_fill = _BRAND if c.trend_reason else _INK_SOFT
    _draw_fit(draw, body, (250, yy + 6, W - 76, y + fzh - 22), body_fill, 30, 22)

    draw.text((44, H - 62), config.PROFILE.CARD_FOOTER_DISCLAIMER,
              font=_font(24), fill=_MUTED)
    return _save(img, out_path)


# ── Candidate cards (3 per stock) ──────────────────────────────────────────
def _card_header(draw, c: Candidate, kind_label: str, step: str) -> int:
    """Prominent header below IG's profile overlay: optional TREND-AKTIE badge, a BIG
    card-type pill (instantly clear whether this is Charttechnik / Fundamental /
    Gesamtbild), then ticker + name. Returns the y to continue drawing at."""
    m = c.metrics
    y = _TOP
    if c.category:  # e.g. "TREND-AKTIE"
        w = draw.textlength(c.category, font=_font(26, bold=True))
        draw.rounded_rectangle((_MARGIN, y, _MARGIN + w + 40, y + 48), radius=12, fill=_BRAND)
        draw.text((_MARGIN + 20, y + 8), c.category, font=_font(26, bold=True), fill=(255, 255, 255))
        y += 66
    kf = _font(46, bold=True)
    kw = draw.textlength(kind_label, font=kf)
    draw.rounded_rectangle((_MARGIN, y, _MARGIN + kw + 56, y + 80), radius=18, fill=_BRAND)
    draw.text((_MARGIN + 28, y + 12), kind_label, font=kf, fill=(255, 255, 255))
    draw.text((W - 150, y + 24), step, font=_font(34, bold=True), fill=_MUTED)
    y += 104
    x = _market_badge(draw, _MARGIN, y + 12, m.market)
    draw.text((x, y), m.ticker, font=_font(58, bold=True), fill=_FG)
    y += 76
    draw.text((_MARGIN, y), f"{m.name}  ·  {m.sector}"[:44], font=_font(28), fill=_MUTED)
    return y + 62


def render_chart_card(c: Candidate, out_path: str) -> str:
    img, draw = _new_card()
    m = c.metrics
    y = _card_header(draw, c, "CHARTTECHNIK", "1/3")

    level, label = ind.tendency(m.tech_score, "chart")
    _signal_badge(draw, _MARGIN, y, level, f"Chart: {label}", big=True)
    ctop = y + 96
    _draw_chart(draw, (_MARGIN, ctop, W - _MARGIN, ctop + 430),
                m.history_closes, c.stop_loss, c.take_profit, c.entry, m.currency)

    # analysis text fills the full container width, between chart and the risk-marks box
    _wrap_px(draw, c.chart_text, _font(38), _MARGIN, ctop + 460, W - _MARGIN, _FG, 50)

    ry = 1474  # fixed so the box always clears the footer, whatever the text length
    draw.rounded_rectangle((_MARGIN, ry, W - _MARGIN, ry + 226), radius=24, fill=_CARD)
    draw.text((90, ry + 20), "Charttechnische Marken (keine Empfehlung)",
              font=_font(28, bold=True), fill=_MUTED)
    _level_row(draw, ry + 76, "Referenz (Schluss)", f"{c.entry:.2f} {m.currency}", _FG)
    _level_row(draw, ry + 128, "Risikomarke (Stop)", f"{c.stop_loss:.2f} {m.currency}", _RED)
    _level_row(draw, ry + 180, "Potenzialmarke (Ziel)", f"{c.take_profit:.2f} {m.currency}", _ACCENT)
    return _save(img, out_path)


def _fig(value, suffix="", pct=False):
    if value is None:
        return "n/a"
    if pct:
        return f"{value * 100:.0f} %"
    return f"{value:.1f}{suffix}".replace(".", ",")


def render_fundamental_card(c: Candidate, out_path: str) -> str:
    img, draw = _new_card()
    m = c.metrics
    y = _card_header(draw, c, "FUNDAMENTAL", "2/3")

    level, label = ind.tendency(m.fund_score, "fund")
    _signal_badge(draw, _MARGIN, y, level, f"Fundamental: {label}", big=True)

    y += 96
    draw.rounded_rectangle((_MARGIN, y, W - _MARGIN, y + 300), radius=24, fill=_CARD)
    draw.text((90, y + 22), "Kennzahlen (einfach erklärt)", font=_font(28, bold=True), fill=_MUTED)
    _level_row(draw, y + 80, "KGV (Preis je € Gewinn)", _fig(m.pe), _FG)
    _level_row(draw, y + 134, "Umsatzwachstum", _fig(m.revenue_growth, pct=True), _FG)
    _level_row(draw, y + 188, "Gewinnmarge", _fig(m.profit_margin, pct=True), _FG)
    _level_row(draw, y + 242, "Fundamental-Score", f"{m.fund_score:.2f}", _LIGHT[level])

    _wrap_px(draw, c.fundamental_text, _font(42), _MARGIN, y + 348, W - _MARGIN, _FG, 54)
    return _save(img, out_path)


def render_overall_card(c: Candidate, out_path: str) -> str:
    img, draw = _new_card()
    m = c.metrics
    y = _card_header(draw, c, "GESAMTBILD", "3/3")

    o_level, o_label = ind.tendency(m.blended, "overall")
    _signal_badge(draw, _MARGIN, y, o_level, f"Gesamtbild: {o_label}", big=True)

    # recap of the two dimensions as small lights
    y += 96
    draw.rounded_rectangle((_MARGIN, y, W - _MARGIN, y + 200), radius=24, fill=_CARD)
    c_level, c_label = ind.tendency(m.tech_score, "chart")
    f_level, f_label = ind.tendency(m.fund_score, "fund")
    _signal_badge(draw, 90, y + 30, c_level, f"Charttechnik — {c_label}")
    _signal_badge(draw, 90, y + 110, f_level, f"Fundamental — {f_label}")

    y += 260
    if c.trend_reason:
        y = _wrap_px(draw, f"Im Trend: {c.trend_reason}", _font(34), _MARGIN, y, W - _MARGIN, _BLUE, 46)
        y += 18
    _wrap_px(draw, c.overall_text, _font(44), _MARGIN, y, W - _MARGIN, _FG, 56)
    return _save(img, out_path)


# ── Earnings + overview cards (light "story" templates) ────────────────────
_LT_BG = (243, 241, 235)      # cream page
_LT_CARD = (255, 255, 255)    # white row card
_LT_INK = (22, 27, 32)        # dark text
_LT_GREY = (140, 148, 156)    # muted grey (sector, footer)
_LT_BADGE = (26, 28, 32)      # dark US/EU badge
_LT_PILL = (233, 231, 224)    # light grey pill (vorbörslich)
_LT_INFO = (230, 240, 251)    # light-blue info banner
_LT_TIMEBOX = (238, 234, 226)  # beige box behind the "ANALYSE IN MEINER STORY" time

# Trailing tokens dropped from a company name for a clean display label.
_NAME_DROP = {"AG", "SE", "N", "V", "NV", "SA", "S.A.", "PLC", "AB", "ASA", "OYJ", "SPA",
              "INC", "INC.", "CORP", "CORP.", "CORPORATION", "CO", "CO.", "COMPANY",
              "INTERNATIONAL", "COMMUNICATIONS", "HOLDING", "HOLDINGS", "GROUP",
              "ACT.A", "ACT", "A", "THE", "LTD", "LTD.", "LIMITED"}


def _clean_name(name: str) -> str:
    """Drop legal/share-class suffixes and de-shout ALL-CAPS names for a clean label
    (e.g. 'VOLKSWAGEN AG V' → 'Volkswagen', 'BNP PARIBAS ACT.A' → 'BNP Paribas')."""
    toks = name.replace(",", " ").split()
    # drop legal/share-class suffixes, dangling connectors/stray letters, AND stock-exchange
    # descriptors at the end — incl. par-value tokens with digits — so e.g.
    # 'Wells Fargo & Company' → 'Wells Fargo', 'SAP SE I' → 'SAP',
    # 'Shell PLC ORD Eur0.07' → 'Shell'
    tail_drop = _NAME_DROP | {"&", "AND", "UND", "+", "I", "II", "III",
                              "ORD", "ORD.", "REG", "REGISTERED", "NPV", "SHS", "CLASS", "CL"}

    def _junk(tok: str) -> bool:
        return tok.upper() in tail_drop or any(ch.isdigit() for ch in tok)

    while len(toks) > 1 and _junk(toks[-1]):
        toks.pop()
    if name.isupper():   # keep short acronyms upper (BNP), title-case the rest
        toks = [t if (len(t) <= 3 and t.isalpha()) else t.capitalize() for t in toks]
    return " ".join(toks)


def _truncate_px(draw, text: str, font, maxw: int) -> str:
    if draw.textlength(text, font=font) <= maxw:
        return text
    while text and draw.textlength(text + "…", font=font) > maxw:
        text = text[:-1]
    return text + "…" if text else text


def _fit_name(draw, text: str, maxw: int, max_sz: int = 42, min_sz: int = 32):
    """Return (font, text) that fits `text` into `maxw`: shrink the font from max_sz
    down to min_sz first, and only truncate as a last resort — so full company names
    (e.g. 'Johnson & Johnson') stay readable instead of being clipped."""
    for sz in range(max_sz, min_sz - 1, -2):
        f = _font(sz, bold=True)
        if draw.textlength(text, font=f) <= maxw:
            return f, text
    f = _font(min_sz, bold=True)
    return f, _truncate_px(draw, text, f, maxw)


def _brandmark(draw, x: int, y: int) -> None:
    """Small radar icon + channel wordmark (dark, on the light template)."""
    draw.ellipse((x, y, x + 50, y + 50), outline=_LT_INK, width=5)
    draw.ellipse((x + 30, y + 8, x + 46, y + 24), fill=_BRAND)
    draw.text((x + 70, y + 8), config.PROFILE.WORDMARK, font=_font(34, bold=True), fill=_LT_INK)


def _pill_right(draw, right_x: int, y: int, text: str, bg, fg, fsize: int = 28) -> int:
    f = _font(fsize, bold=True)
    w = draw.textlength(text, font=f)
    h = int(fsize * 1.85)
    x0 = int(right_x - w - 52)
    draw.rounded_rectangle((x0, y, right_x, y + h), radius=h // 2, fill=bg)
    draw.text((x0 + 26, y + int(h * 0.24)), text, font=f, fill=fg)
    return x0


def _dark_badge(draw, x: int, y: int, market: str) -> int:
    w, h = 76, 60
    draw.rounded_rectangle((x, y, x + w, y + h), radius=14, fill=_LT_BADGE)
    t = market or "US"
    tf = _font(28, bold=True)
    draw.text((x + (w - draw.textlength(t, font=tf)) / 2, y + 14), t, font=tf, fill=(255, 255, 255))
    return x + w


def _lt_footer(draw) -> None:
    draw.text((44, H - 62), config.PROFILE.CARD_FOOTER_DISCLAIMER,
              font=_font(20), fill=_LT_GREY)
    hf = _font(22, bold=True)
    draw.text((W - 44 - draw.textlength(config.BRAND_HANDLE, font=hf), H - 63),
              config.BRAND_HANDLE, font=hf, fill=_LT_INK)


def _lt_head(draw, pill_text: str, title: str, sub_segments: list[tuple]) -> int:
    """Shared header: radar wordmark (left) + blue pill (right) + big title + subtitle.
    Fixed headline size so short titles stay on one line and long ones wrap (like the
    templates). Returns the y below the subtitle; kept clear of IG's top profile overlay."""
    _brandmark(draw, 60, 172)
    _pill_right(draw, W - 56, 170, pill_text, _BRAND, (255, 255, 255), 28)
    hf, lh, y = _font(76, bold=True), 88, 252
    for line in _wrap_lines_px(draw, title, hf, W - 130):
        draw.text((60, y), line, font=hf, fill=_LT_INK)
        y += lh
    x, sf = 62, _font(30, bold=True)
    for text, color in sub_segments:
        draw.text((x, y + 6), text, font=sf, fill=color)
        x += draw.textlength(text, font=sf)
    return y + 60


def render_earnings_card(items: list[EarningsItem], out_path: str, day_label: str) -> str:
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (W, H), _LT_BG)
    draw = ImageDraw.Draw(img)
    y = _lt_head(draw, "EARNINGS", "Quartalszahlen heute", [(day_label, _BRAND)]) + 20

    if not items:
        draw.text((60, y + 10), "Heute keine relevanten Termine.", font=_font(40), fill=_LT_GREY)
        _lt_footer(draw)
        return _save(img, out_path)

    nf = _font(46, bold=True)
    for it in items[:7]:
        lines = _wrap_lines_px(draw, _clean_name(it.name) or it.ticker, nf, 560)[:2]
        ch = 150 if len(lines) == 1 else 202
        draw.rounded_rectangle((60, y, W - 60, y + ch), radius=24, fill=_LT_CARD)
        draw.rounded_rectangle((62, y + 18, 74, y + ch - 18), radius=6, fill=_BRAND)   # accent bar
        bx = _dark_badge(draw, 104, y + ch // 2 - 30, it.market)
        tx = bx + 34
        block_h = len(lines) * 54 + 42
        ty = y + (ch - block_h) // 2
        for ln in lines:
            draw.text((tx, ty), ln, font=nf, fill=_LT_INK)
            ty += 54
        draw.text((tx, ty + 2), it.ticker, font=_font(30, bold=True), fill=_BRAND)
        if it.when:
            _pill_right(draw, W - 92, y + ch // 2 - 26, it.when, _LT_PILL, (108, 114, 122), 26)
        y += ch + 20
        if y > H - 220:
            break
    _lt_footer(draw)
    return _save(img, out_path)


def render_candidates_overview_card(candidates: list[Candidate], out_path: str) -> str:
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (W, H), _LT_BG)
    draw = ImageDraw.Draw(img)
    y = _lt_head(draw, "WATCHLIST", "Auf der Watchlist heute",
                 [("Charttechnik + Fundamental", _BRAND),
                  ("  ·  verschiedene Branchen", _LT_GREY)]) + 8

    # info banner: the detail analyses go live at the per-stock times shown on the right
    info = "Detailanalysen erscheinen heute zur angegebenen Uhrzeit in der Story"
    inf = _font(21, bold=True)
    bx1 = min(W - 60, 60 + int(draw.textlength(info, font=inf)) + 92)
    draw.rounded_rectangle((60, y, bx1, y + 58), radius=29, fill=_LT_INFO)
    draw.ellipse((90, y + 21, 104, y + 35), fill=_BRAND)
    draw.text((120, y + 16), info, font=inf, fill=_BRAND)
    y += 60 + 26

    # assign each stock its posting time (EU slots fill first, then US — matching how
    # publish_next_candidate_group posts them), then order the list CHRONOLOGICALLY so
    # the card reads top-to-bottom in the exact sequence the stories go live.
    eu, us = list(config.STORY_SLOTS_EU), list(config.STORY_SLOTS_US)
    ei = ui = 0
    timed: list[tuple[str, object]] = []
    for c in candidates[:5]:
        if c.metrics.market == "EU":
            t = eu[min(ei, len(eu) - 1)] if eu else ""
            ei += 1
        else:
            t = us[min(ui, len(us) - 1)] if us else ""
            ui += 1
        timed.append((t, c))
    timed.sort(key=lambda p: p[0] or "99:99")

    tkf, sf, lf = _font(27, bold=True), _font(26), _font(24, bold=True)
    for t, c in timed:
        m = c.metrics
        ch = 196
        draw.rounded_rectangle((60, y, W - 60, y + ch), radius=28, fill=_LT_CARD)
        _dark_badge(draw, 92, y + ch // 2 - 30, m.market)   # badge vertically centered
        tx = 196
        nf, name = _fit_name(draw, _clean_name(m.name), 470)   # full name, shrink before clipping
        w_name = draw.textlength(name, font=nf)
        w_tk = draw.textlength(m.ticker, font=tkf)
        w_sec = draw.textlength(m.sector, font=sf)
        c_lvl, c_lab = ind.tendency(m.tech_score, "chart")
        f_lvl, f_lab = ind.tendency(m.fund_score, "fund")
        inline = (w_name + 18 + w_tk + 22 + w_sec) <= (760 - tx)   # sector fits on the name line?

        if inline:
            ty = y + (ch - 96) // 2
            draw.text((tx, ty), name, font=nf, fill=_LT_INK)
            draw.text((tx + w_name + 18, ty + 12), m.ticker, font=tkf, fill=_BRAND)
            draw.text((tx + w_name + 18 + w_tk + 22, ty + 14), m.sector, font=sf, fill=_LT_GREY)
            ay = ty + 66
        else:
            ty = y + (ch - 130) // 2
            draw.text((tx, ty), name, font=nf, fill=_LT_INK)
            draw.text((tx + w_name + 18, ty + 12), m.ticker, font=tkf, fill=_BRAND)
            draw.text((tx, ty + 50), _truncate_px(draw, m.sector, sf, 520), font=sf, fill=_LT_GREY)
            ay = ty + 100
        draw.ellipse((tx, ay, tx + 19, ay + 19), fill=_LIGHT[c_lvl])
        draw.text((tx + 28, ay - 4), f"Chart: {c_lab}", font=lf, fill=_LT_INK)
        x2 = tx + 28 + draw.textlength(f"Chart: {c_lab}", font=lf) + 28
        draw.ellipse((x2, ay, x2 + 19, ay + 19), fill=_LIGHT[f_lvl])
        draw.text((x2 + 28, ay - 4), f"Fundamental: {f_lab}", font=lf, fill=_LT_INK)

        # right time box: light beige rounded box with "ANALYSE IN MEINER STORY" + big time
        if t:
            bx0, bx1 = 788, W - 88
            draw.rounded_rectangle((bx0, y + 28, bx1, y + ch - 28), radius=18, fill=_LT_TIMEBOX)
            cx = (bx0 + bx1) // 2
            llf = _font(19, bold=True)
            for i, ln in enumerate(("ANALYSE IN", "MEINER STORY")):
                draw.text((cx - draw.textlength(ln, font=llf) / 2, y + 52 + i * 24),
                          ln, font=llf, fill=_LT_GREY)
            tf = _font(48, bold=True)
            draw.text((cx - draw.textlength(t, font=tf) / 2, y + 112), t, font=tf, fill=_BRAND)
        y += ch + 20
        if y > H - 210:
            break
    _lt_footer(draw)
    return _save(img, out_path)


# ── Milestone story (template "story-meilenstein") ─────────────────────────
def _de_num(n: int) -> str:
    return f"{n:,}".replace(",", ".")

# ── Follower-milestone story — Claude-Design "Story-Milestone v2" ──────────
# High-fidelity rebuild of the design handoff: near-black stage, elliptical
# accent glow, radar rings, fixed confetti, an offset outline copy of the big
# number, progress card and share CTA. Canvas 1080×1920, 68 px side margin,
# 170 px Instagram safe zone at the top.
# Only the ACCENT is channel-specific (PROFILE.MILESTONE_ACCENT, default: the
# palette blue) — the near-black stage and the layout are brand-neutral.
_MS_PAGE = (12, 21, 18)                       # #0c1512 stage
_MS_CENTER = (540, 700)                       # radar-ring centre
_MS_RINGS = (230, 340, 460, 590, 730)
# 14 fixed confetti shapes (x, y, kind, size, rotation) — no randomness, so the
# same milestone always exports identically
_MS_CONFETTI = (
    (120, 380, "sq", 22, 12), (960, 430, "dot", 14, 0), (180, 620, "plus", 26, -18),
    (925, 660, "sq", 18, -8), (90, 900, "dot", 11, 0), (995, 950, "plus", 22, 14),
    (150, 1120, "sq", 16, 24), (935, 1160, "dot", 13, 0), (250, 300, "dot", 9, 0),
    (830, 320, "sq", 13, -14), (60, 520, "plus", 18, 8), (1010, 560, "sq", 15, 20),
    (300, 1215, "plus", 20, -10), (790, 1240, "dot", 10, 0),
)
_MS_CURVE = ((-40, 1830), (190, 1755), (400, 1805), (640, 1680), (850, 1730), (1120, 1590))
_MS_SHARE_HINT = "Sendet den Kanal an jemanden, der neue Beiträge mag."


def _ms_font(size: int, weight: int = 700):
    return branding.load_weighted_font(size, weight)


def _ms_accent():
    """Accent of the milestone card. The design ships four approved accents, so
    a channel may override the palette blue via PROFILE.MILESTONE_ACCENT."""
    raw = getattr(config.PROFILE, "MILESTONE_ACCENT", None)
    if isinstance(raw, str) and len(raw) == 7 and raw.startswith("#"):
        return tuple(int(raw[i:i + 2], 16) for i in (1, 3, 5))
    if isinstance(raw, (tuple, list)) and len(raw) == 3:
        return tuple(int(v) for v in raw)
    return _BRAND


def _wa(alpha: float) -> tuple:
    """White at `alpha` — the design expresses every tint as rgba(255,255,255,x)."""
    return (255, 255, 255, int(round(alpha * 255)))


def _tracked_w(draw, text: str, font, tracking: float) -> float:
    """Advance width of `text` with CSS letter-spacing — which adds the spacing
    after EVERY character, including the last. That trailing gap is what shifts
    centred tracked text off the optical middle in the design reference, so we
    reproduce it instead of centring the ink."""
    return sum(draw.textlength(c, font=font) for c in text) + tracking * len(text)


def _ink_y(font, text: str, ink_top: float) -> float:
    """Draw-y at which the VISIBLE ink of `text` starts exactly at `ink_top`.
    Anchoring on ink (not on the ascender box) is what makes the rebuild line up
    with the design reference regardless of the font's internal metrics."""
    return ink_top - font.getbbox(text)[1]


def _tracked(draw, x: float, y: float, text: str, font, fill, tracking: float = 0.0) -> float:
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill)
        x += draw.textlength(ch, font=font) + tracking
    return x


def _tracked_center(draw, text: str, font, ink_top: float, fill, tracking: float = 0.0) -> None:
    w = _tracked_w(draw, text, font, tracking)
    _tracked(draw, (W - w) / 2, _ink_y(font, text, ink_top), text, font, fill, tracking)


def _ms_stage(accent):
    """Near-black page + the elliptical accent glow (radialGradient cx 50 %,
    cy 36 %, r 55 %; accent .42 -> .08 at 60 % -> 0). Drawn as nested opaque
    ellipses from the outside in, so nothing alpha-stacks."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (W, H), _MS_PAGE)
    draw = ImageDraw.Draw(img)
    cx, cy, rx, ry = W / 2, H * 0.36, W * 0.55, H * 0.55
    steps = 400
    for i in range(steps, 0, -1):
        t = i / steps
        op = (0.42 + (0.08 - 0.42) * (t / 0.6)) if t <= 0.6 else 0.08 * (1 - (t - 0.6) / 0.4)
        col = tuple(int(round(_MS_PAGE[k] + (accent[k] - _MS_PAGE[k]) * op)) for k in range(3))
        draw.ellipse((cx - rx * t, cy - ry * t, cx + rx * t, cy + ry * t), fill=col)
    return img


def _ms_confetti(layer, accent) -> None:
    from PIL import Image, ImageDraw

    draw = ImageDraw.Draw(layer)
    for i, (x, y, kind, s, rot) in enumerate(_MS_CONFETTI):
        col = accent + (166,) if i % 3 == 0 else _wa(0.30)
        if kind == "dot":
            draw.ellipse((x - s, y - s, x + s, y + s), fill=col)
            continue
        pad = s * 2 + 12
        tile = Image.new("RGBA", (pad * 2, pad * 2), (0, 0, 0, 0))
        td = ImageDraw.Draw(tile)
        if kind == "sq":
            td.rounded_rectangle((pad - s, pad - s, pad + s, pad + s), radius=4, fill=col)
        else:  # plus
            td.line((pad - s, pad, pad + s, pad), fill=col, width=6)
            td.line((pad, pad - s, pad, pad + s), fill=col, width=6)
        layer.alpha_composite(tile.rotate(rot, resample=Image.BICUBIC),
                              (int(x - pad), int(y - pad)))


def _ms_deco(img, accent):
    """Radar rings, confetti and the bottom price curve — everything behind the
    content, drawn once on an RGBA layer and composited."""
    from PIL import Image, ImageDraw

    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    cx, cy = _MS_CENTER
    for i, r in enumerate(_MS_RINGS):
        draw.ellipse((cx - r, cy - r, cx + r, cy + r),
                     outline=_wa(0.09 - i * 0.012), width=3)
    _ms_confetti(layer, accent)
    draw.polygon([(0, H), *_MS_CURVE, (W, H)], fill=accent + (36,))
    draw.line(list(_MS_CURVE), fill=accent + (128,), width=9, joint="curve")
    return Image.alpha_composite(img.convert("RGBA"), layer)


def _ms_share_icon(draw, cx: float, cy: float) -> None:
    """The 24x24 share glyph from the handoff, scaled to 44 px."""
    k = 44 / 24

    def p(x, y):
        return (cx - 22 + x * k, cy - 22 + y * k)

    white, w = (255, 255, 255), 5
    draw.line([p(4, 12), p(4, 19), p(5, 20), p(19, 20), p(20, 19), p(20, 12)],
              fill=white, width=w, joint="curve")
    draw.line([p(12, 16), p(12, 3)], fill=white, width=w)
    draw.line([p(7, 8), p(12, 3), p(17, 8)], fill=white, width=w, joint="curve")


def render_milestone_story(milestone: int, next_milestone: int, out_path: str,
                           current: int | None = None) -> str:
    """Follower-milestone thank-you card (design: story-meilenstein.png).
    `current` is the real follower count driving the progress bar; it defaults to
    the milestone itself. Every number is dynamic, so the same card serves 100,
    1.000 or 100.000 followers.

    Drawing order: opaque stage → decoration → panels → text. Text goes on its
    own RGBA layer because most of it is white at 40–90 % opacity; drawing that
    straight onto RGB would silently render it as solid white."""
    from PIL import Image, ImageDraw

    accent = _ms_accent()
    stand = milestone if current is None else max(current, milestone)
    num, goal = _de_num(milestone), _de_num(next_milestone)
    missing = _de_num(max(0, next_milestone - stand))
    pct = min(100, max(5, round(stand / max(next_milestone, 1) * 100)))
    hint = getattr(config.PROFILE, "MILESTONE_SHARE_HINT", None) or _MS_SHARE_HINT

    img = _ms_deco(_ms_stage(accent), accent)
    m = ImageDraw.Draw(img)                     # measuring only

    # ── panels: logo rings, badge outline, goal card, progress bar, CTA ────
    badge, bf = "MEILENSTEIN", _ms_font(21, 800)
    bx0 = 1012 - _tracked_w(m, badge, bf, 3.36) - 40
    panels = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    pd = ImageDraw.Draw(panels)
    pd.ellipse((68, 176, 118, 226), outline=_wa(0.30), width=4)
    pd.ellipse((81, 189, 105, 213), outline=_wa(0.55), width=4)
    pd.ellipse((104, 181, 118, 195), fill=accent + (255,))
    pd.rounded_rectangle((bx0, 178, 1012, 224), radius=23, outline=accent + (255,), width=2)
    pd.rounded_rectangle((68, 985, 1012, 1195), radius=30, fill=_wa(0.06),
                         outline=_wa(0.10), width=2)
    pd.rounded_rectangle((106, 1092, 974, 1118), radius=13, fill=_wa(0.10))
    pd.rounded_rectangle((106, 1092, 106 + (974 - 106) * pct / 100, 1118), radius=13,
                         fill=accent + (255,))
    pd.rounded_rectangle((68, 1220, 1012, 1376), radius=30, fill=accent + (255,))
    img = Image.alpha_composite(img, panels)

    # the icon tile is white 20 % ON the CTA card, so it composites separately
    tile = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(tile).rounded_rectangle((106, 1256, 190, 1340), radius=24, fill=_wa(0.20))
    img = Image.alpha_composite(img, tile)

    # ── big number: 300 px per design, shrunk only if it would not fit ─────
    # "1.000" fits at the design size; "100.000" would run off the canvas, so
    # anything wider than the content column steps down and is re-centred
    # vertically inside the design's number band (ink 361 … 574).
    size, track = 300, -15.0
    while size > 120:
        nf = _ms_font(size, 900)
        track = -0.05 * size                    # letter-spacing -0.05em
        nw = _tracked_w(m, num, nf, track)
        if nw <= W - 2 * 68:
            break
        size -= 4
    top, bottom = nf.getbbox(num)[1], nf.getbbox(num)[3]
    nx = (W - nw) / 2
    ny = 361 + (213 - (bottom - top)) / 2 - top
    off, stroke = round(size * 14 / 300), max(2, round(size * 3 / 300))

    ghost = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(ghost)
    x = nx + off                                # decorative offset outline copy
    for ch in num:
        gd.text((x, ny + off), ch, font=nf, fill=(0, 0, 0, 0),
                stroke_width=stroke, stroke_fill=_wa(0.16))
        x += m.textlength(ch, font=nf) + track
    img = Image.alpha_composite(img, ghost)

    # ── text layer ─────────────────────────────────────────────────────────
    text = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(text)
    white, acc = _wa(1.0), accent + (255,)

    wf, wm = _ms_font(27, 900), config.PROFILE.WORDMARK
    _tracked(draw, 134, _ink_y(wf, wm, 190), wm, wf, white, 0.81)
    _tracked(draw, bx0 + 20, _ink_y(bf, badge, 192), badge, bf, acc, 3.36)

    _tracked_center(draw, "GEKNACKT", _ms_font(30, 800), 305, _wa(0.50), 7.2)
    _tracked(draw, nx, ny, num, nf, white, track)

    ff = _ms_font(60, 900)
    fw = _tracked_w(draw, "FOLLOWER", ff, 3.6)
    fx = (W - fw) / 2
    _tracked(draw, fx, _ink_y(ff, "FOLLOWER", 633), "FOLLOWER", ff, acc, 3.6)
    for x0 in (fx - 92, fx + fw + 22):          # the 70×4 rules left and right
        draw.rounded_rectangle((x0, 652, x0 + 70, 656), radius=2, fill=acc)

    _tracked_center(draw, "Ihr seid die Besten!", _ms_font(78, 900), 760, white, -1.95)
    sf = _ms_font(30, 600)
    for i, line in enumerate(("Danke für euer Vertrauen, jedes Like und jede Nachricht.",
                              config.PROFILE.MILESTONE_TAGLINE)):
        _tracked_center(draw, line, sf, 861 + i * 44, _wa(0.68))

    lf = _ms_font(24, 800)
    _tracked(draw, 106, _ink_y(lf, "NÄCHSTES ZIEL", 1051), "NÄCHSTES ZIEL", lf, _wa(0.50), 2.4)
    gf = _ms_font(54, 900)
    draw.text((974 - draw.textlength(goal, font=gf), _ink_y(gf, goal, 1025)), goal,
              font=gf, fill=acc)
    rest = f"Nur noch {missing} bis {goal} – das schaffen wir!"
    rf = _ms_font(26, 800)
    draw.text((106, _ink_y(rf, rest, 1138)), rest, font=rf, fill=white)

    _ms_share_icon(draw, 148, 1298)
    tf = _ms_font(42, 900)
    draw.text((218, _ink_y(tf, "Teilt diese Story!", 1260)), "Teilt diese Story!",
              font=tf, fill=white)
    hf = _ms_font(26, 600)
    draw.text((218, _ink_y(hf, hint, 1311)), hint, font=hf, fill=_wa(0.90))

    foot, lff = config.PROFILE.MILESTONE_FOOTER, _ms_font(22, 600)
    draw.text((68, _ink_y(lff, foot, 1853)), foot, font=lff, fill=_wa(0.40))
    rff, handle = _ms_font(22, 700), config.BRAND_HANDLE
    draw.text((1012 - draw.textlength(handle, font=rff), _ink_y(rff, handle, 1853)),
              handle, font=rff, fill=_wa(0.50))

    return _save(Image.alpha_composite(img, text).convert("RGB"), out_path)
