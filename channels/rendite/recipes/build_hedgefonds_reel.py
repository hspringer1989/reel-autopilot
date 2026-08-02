"""Custom story REEL: how a 25-year-old ex-OpenAI researcher went from the
best-performing large fund in the world (+439% net) to a forced fire sale of his
entire public equity book in two days — and why being RIGHT did not save him.

Bright yellow-balloon opener (hero, about to pop) + colorful paint CTA, four
branded frames. Educational only, no advice, no judgement about the person.

Sources (verified 01.08.2026): CNBC 31.07.2026 ($45B -> ~$10B, fire sale to
Citadel), Yahoo Finance / QZ (margin calls Goldman Sachs, JPMorgan, BofA;
leverage up to 4x; SK Hynix, CoreWeave, Micron, Nebius, Sandisk), FT via
Handelsblatt (+439% net through 30.06.2026), financefeeds ($225M seed, 6-day
margin call), n-tv (German summary).
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

# ── voice: flüssiger + etwas schneller auf Userwunsch (01.08.2026).
# Niedrigere Stability = lebendiger/weniger monoton; Speed leicht angehoben.
config.ELEVENLABS_STABILITY = 0.35
config.ELEVENLABS_STYLE = 0.40
config.ELEVENLABS_SPEED = 1.10

# opener: roller coaster car at the very top of the drop against a deep blue sky —
# bright, iconic, and literally "about to plunge" (user rejected the balloon idea)
_OPENER_ID = int(os.getenv("OPENER_ID", "11067600"))
# CTA: bright multicoloured confetti on white — deliberately NOT the paint clip
# again (user asked for variety in the closing shot)
_CTA_ID = int(os.getenv("CTA_ID", "8516638"))

W, H = 1080, 1920
F = branding.load_font
BG, CARD, BLUE, BLUEL, FG, MUTED = (branding.BG, branding.CARD, branding.BLUE,
                                    branding.BLUE_LIGHT, branding.FG, branding.MUTED)
RED, GREEN, AMBER = branding.RED, branding.GREEN, branding.AMBER

STAND = "Stand: 1. August 2026 · Quellen: CNBC · FT · Handelsblatt"


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


# Safe band: IG overlays the top ~290px, subtitles sit at MarginV=500
# (~y1260-1420) → every layout below is pre-computed to end at y ≤ 1250.
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


def _note(d, y, head, text, head_col, bg, h=186):
    """Explainer box. Returns y after the box."""
    d.rounded_rectangle((60, y, W - 60, y + h), radius=20, fill=bg)
    d.text((92, y + 20), head, font=F(30, bold=True), fill=head_col)
    branding.wrap(d, text, F(31), 92, y + 70, 44, FG, 44)
    return y + h


def _save(img, name) -> str:
    out = Path(config.OUTPUT_DIR) / name
    img.save(out, quality=92)
    return str(out)


def frame_rise() -> str:
    """The rise: who he is and the number nobody believes."""
    img, d = _canvas()
    _kicker(d, "DER AUFSTIEG")
    _title(d, "Der beste große Fonds")
    _title(d, "der Welt", y=TOP + 150)
    rows = [("Leopold Aschenbrenner", "25 Jahre, Ex-OpenAI-Forscher", ""),
            ("Fonds gegründet", "2024, mit rund 225 Mio. $", ""),
            ("Berufserfahrung in Finanz", "keine", ""),
            ("Rendite bis 30.06.2026", "netto", "+439 %")]
    y, ch, gap = 560, 112, 12
    for name, sub, val in rows:
        d.rounded_rectangle((60, y, W - 60, y + ch), radius=20, fill=CARD)
        d.text((92, y + 20), name, font=F(36, bold=True), fill=FG)
        d.text((92, y + 70), sub, font=F(27), fill=MUTED)
        if val:
            _rtext(d, W - 92, y + 34, val, F(54, bold=True), GREEN)
        y += ch + gap
    _note(d, y + 8, "Aus 225 Millionen wurden",
          "rund 45 Milliarden Dollar — kein großer Fonds lief besser.",
          GREEN, (20, 40, 32), h=170)
    _footer(d)
    return _save(img, "hf_frame_rise.jpg")


def frame_bet() -> str:
    """The bet — and the twist: the thesis was right."""
    img, d = _canvas()
    _kicker(d, "DIE WETTE")
    _title(d, "Alles auf eine Idee:")
    _title(d, "KI braucht Hardware", y=TOP + 150)
    rows = [("Speicher-Chips", "SK Hynix · Micron · Sandisk"),
            ("Rechenzentren & Cloud", "CoreWeave · Nebius"),
            ("Dazu: Wetten GEGEN Software", "die nicht aufgingen")]
    y, ch, gap = 520, 132, 16
    for name, sub in rows:
        d.rounded_rectangle((60, y, W - 60, y + ch), radius=20, fill=CARD)
        d.text((92, y + 24), name, font=F(36, bold=True), fill=FG)
        d.text((92, y + 76), sub, font=F(29), fill=BLUEL)
        y += ch + gap
    _note(d, y + 10, "Und jetzt das Verrückte",
          "Mit dieser Grundidee lag er richtig. KI braucht wirklich "
          "Chips, Speicher und Strom.", BLUEL, (24, 32, 44))
    _footer(d)
    return _save(img, "hf_frame_bet.jpg")


def frame_leverage() -> str:
    """The mechanism that killed him: leverage."""
    img, d = _canvas()
    _kicker(d, "DER HEBEL", AMBER)
    _title(d, "Warum Recht haben")
    _title(d, "nicht gereicht hat", y=TOP + 150)
    rows = [("Eigenes Kapital", "1 €", BLUEL),
            ("Damit investiert", "bis 4 €", AMBER),
            ("Kurs fällt 25 %", "Eigenkapital weg", RED)]
    y, ch, gap = 520, 130, 16
    for name, val, col in rows:
        d.rounded_rectangle((60, y, W - 60, y + ch), radius=20, fill=CARD)
        d.text((92, y + 40), name, font=F(38, bold=True), fill=FG)
        _rtext(d, W - 92, y + 32, val, F(48, bold=True), col)
        y += ch + gap
    _note(d, y + 10, "Hebel bis zum Vierfachen",
          "Er vervierfacht Gewinne — und Verluste. Er ändert nicht, "
          "ob du recht hast, sondern wie lange du durchhältst.", AMBER, (44, 36, 20))
    _footer(d)
    return _save(img, "hf_frame_leverage.jpg")


def frame_call() -> str:
    """The collapse: margin calls and the fire sale."""
    img, d = _canvas()
    _kicker(d, "DER ABSTURZ", RED)
    _title(d, "Zwei Tage, und das")
    _title(d, "Depot war weg", y=TOP + 150)
    rows = [("Juli: Chip-Sektor", "schlechtester Monat seit 2008"),
            ("Banken fordern Geld nach", "Goldman Sachs · JPMorgan · BofA"),
            ("30./31. Juli: Notverkauf", "gesamtes Aktienbuch an Citadel"),
            ("Vermögen", "45 Mrd. $  →  rund 10 Mrd. $")]
    y, ch, gap = 520, 118, 12
    for name, sub in rows:
        d.rounded_rectangle((60, y, W - 60, y + ch), radius=20, fill=CARD)
        d.text((92, y + 18), name, font=F(35, bold=True), fill=FG)
        d.text((92, y + 66), sub, font=F(28), fill=RED)
        y += ch + gap
    _note(d, y + 8, "Margin Call",
          "Wer die geforderten Sicherheiten nicht nachzahlen kann, "
          "wird zwangsweise verkauft — zum Preis des Tages.", RED, (44, 24, 28))
    _footer(d)
    return _save(img, "hf_frame_call.jpg")


# Voiceover: numbers ALWAYS as words, concrete dates spoken (reels stay online).
_TEXTS = [
    "Ein fünfundzwanzigjähriger Deutscher hatte den besten großen Fonds der Welt. "
    "Am dreißigsten und einunddreißigsten Juli musste er sein komplettes "
    "Aktienportfolio verkaufen.",

    "Leopold Aschenbrenner forschte bei OpenAI an KI-Sicherheit. Zweitausendvierundzwanzig "
    "gründete er seinen eigenen Fonds, ohne einen Tag Berufserfahrung in der Finanzbranche. "
    "Bis Ende Juni stand er bei vierhundertneununddreißig Prozent Plus.",

    "Seine Wette: Wenn KI stärker wird, braucht sie Chips, Speicher und Rechenzentren. "
    "Also kaufte er genau das. Und das Verrückte ist: Damit lag er richtig.",

    "Aber er arbeitete mit Hebel, bis zum Vierfachen. Für jeden eigenen Euro waren vier "
    "investiert. Das vervierfacht Gewinne, und eben auch Verluste. Fällt der Kurs um ein "
    "Viertel, ist das eigene Geld weg.",

    "Dann kam der Juli, der schlechteste Chipmonat seit zweitausendacht. Die Banken "
    "forderten Sicherheiten nach. Am einunddreißigsten Juli ging das gesamte Aktienpaket "
    "an den Konkurrenten Citadel, mit Abschlag.",

    "Und genau das ist das Verrückte an der Sache: Seine Idee ging auf, er selbst nicht. "
    "Ohne geliehenes Geld hätte er einfach einen schlechten Monat gehabt. Mit vierfachem "
    "Hebel war es das Ende. Folge für den echten Durchblick an der Börse!",
]

_TITLE = "Vom besten Fonds der Welt zum Notverkauf — in zwei Tagen"

_CAPTION = (
    "💥 Der beste große Fonds der Welt — und dann war das komplette Aktiendepot weg.\n\n"
    "Leopold Aschenbrenner, 25, früher OpenAI-Forscher, gründete 2024 seinen Hedgefonds "
    "„Situational Awareness\" — ohne einen Tag Berufserfahrung in der Finanzbranche.\n\n"
    "📈 Der Aufstieg:\n"
    "· Start mit rund 225 Mio. $\n"
    "· +439 % netto bis 30.06.2026\n"
    "· Vermögen: rund 45 Mrd. $\n\n"
    "🎯 Die Wette: KI braucht Hardware — Speicher (SK Hynix, Micron, Sandisk), "
    "Rechenzentren (CoreWeave, Nebius). Mit dieser Grundidee lag er richtig.\n\n"
    "⚙️ Das Problem: Hebel bis zum 4-Fachen. Für 1 € eigenes Kapital waren bis zu 4 € "
    "investiert — das vervierfacht Gewinne UND Verluste.\n\n"
    "💣 Der Absturz: Im Juli erlebte der Chip-Sektor seinen schlechtesten Monat seit 2008. "
    "Goldman Sachs, JPMorgan und die Bank of America forderten Sicherheiten nach. "
    "Am 30./31. Juli ging das gesamte Aktienbuch mit Abschlag an Citadel. "
    "Aus 45 Mrd. $ wurden rund 10 Mrd. $.\n\n"
    "🧠 Die Lektion: Er hatte recht — und verlor trotzdem fast alles. Beim Hebel zählt "
    "nicht, ob du am Ende richtig liegst, sondern ob du bis dahin durchhältst. "
    "Wer dieselben Aktien ohne geliehenes Geld hielt, hatte nur einen schlechten Monat.\n\n"
    "⚠️ Keine Anlageberatung — nur Bildung & Unterhaltung. Kein Kauf-/Verkaufsaufruf.\n"
    "Quellen: CNBC, Financial Times, Handelsblatt (31.07./01.08.2026)\n"
    "#hedgefonds #ki #aktien #börse #hebel #margincall #risiko #investieren "
    "#finanzwissen #chipaktien"
)


async def _main() -> None:
    opener = _ensure_clip(_OPENER_ID)
    cta = _ensure_clip(_CTA_ID)
    frames = [frame_rise(), frame_bet(), frame_leverage(), frame_call()]
    broll_paths = [opener, frames[0], frames[1], frames[2], frames[3], cta]

    segments = [ScriptSegment(text=t, broll_query="") for t in _TEXTS]
    script = ReelScript(hook=_TEXTS[0], segments=segments, caption=_CAPTION,
                        hashtags=[], title=_TITLE)

    with session_scope() as s:
        reel = ReelRow(trend_id=0,
                       script_json=json.dumps({"topic": "situational awareness fund collapse",
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
    print(f"Hedgefonds-Reel #{rid} fertig: {video}")


if __name__ == "__main__":
    asyncio.run(_main())
