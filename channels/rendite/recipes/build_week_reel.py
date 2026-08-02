"""Build a 'week ahead' market-outlook reel (custom, grounded script — NOT a single-stock
analysis). Fitting Pexels b-roll per segment, smooth TTS, no 'link in bio' CTA.
Persists ReelRow(pending_review) and sends it to Telegram review."""
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

import config
from src.models import ReelScript, ScriptSegment
from src.pipeline import _script_to_json
from src.render.broll import PexelsBroll
from src.render.renderer import pick_music, render_reel
from src.stocks.stock_reel import _spoken_de
from src.storage.database import ReelRow, session_scope
from src.tts.base import get_tts

# (voiceover text, english b-roll search query) — grounded in the real calendar:
# FOMC Wed/Thu 28-29 Jul; MSFT+META Wed 29 Jul, AAPL+AMZN Thu 30 Jul; Alphabet weak this wk.
SEGMENTS = [
    ("Die neue Börsenwoche hat es in sich, denn gleich zwei Ereignisse können die Kurse "
     "kräftig bewegen.",
     "busy stock market trading floor"),
    ("Mittwoch und Donnerstag tagt die US-Notenbank. Die Zinsen bleiben wohl gleich, "
     "spannend ist der Ton. Klingt die Fed weiter hart, geraten zinssensible Werte wie "
     "Immobilienaktien unter Druck. Wird sie entspannter, ist das Rückenwind für den ganzen Markt.",
     "federal reserve building washington"),
    ("Ab Mittwoch wird es heiß: Microsoft und Meta öffnen die Bücher. Alle schauen, ob sich "
     "die riesigen Investitionen in künstliche Intelligenz endlich auszahlen. Überzeugt die "
     "Cloud, ist das die Chance, enttäuschen die Kosten, drohen Rücksetzer.",
     "data center servers technology"),
    ("Donnerstag folgen die Schwergewichte Apple und Amazon. Bei Apple zählen Services und "
     "China, bei Amazon die Cloud-Sparte. Nach den schwachen Signalen von Alphabet ist der "
     "Markt nervös: Ein starkes Ergebnis bringt Erleichterung, ein schwaches könnte den "
     "Techsektor weiter belasten.",
     "smartphone apple store technology"),
    ("Für dich heißt das: Diese Woche entscheidet sich viel an zwei Fronten, Zinsen und Big "
     "Tech. Beides bringt Chancen, aber auch echtes Rückschlagrisiko. Wer die Termine kennt, "
     "wird nicht überrascht.",
     "trader analyzing charts screens"),
    ("Wir behalten die Woche für dich im Blick und melden uns mit den wichtigsten Ergebnissen. "
     "Folg uns, wenn dir solche Einordnungen helfen.",
     "person walking sunny city summer"),
]

CAPTION = (
    "📅 Die neue Börsenwoche im Überblick: der Fed-Zinsentscheid (Mi/Do) und die Earnings der "
    "Tech-Giganten Microsoft, Meta, Apple & Amazon. Zwei Fronten, viele Chancen — und echtes "
    "Rückschlagrisiko. Worauf du achten solltest. 📈\n\n"
    "⚠️ Keine Anlageberatung — nur Bildung & Unterhaltung. Kein Kauf-/Verkaufsaufruf."
)
HASHTAGS = ["#börse", "#aktien", "#wochenausblick", "#fed", "#zinsen", "#bigtech",
            "#apple", "#amazon", "#microsoft", "#meta", "#finanzen", "#investieren", "#renditeradar"]
TITLE = "Die Börsenwoche im Überblick"

segments = [ScriptSegment(text=_spoken_de(t, "", ""), broll_query=q) for t, q in SEGMENTS]
script = ReelScript(hook=segments[0].text, segments=segments,
                    caption=CAPTION, hashtags=HASHTAGS, title=TITLE)

with session_scope() as session:
    reel = ReelRow(trend_id=0, script_json=_script_to_json(script),
                   caption=f"{script.caption}\n\n{' '.join(script.hashtags)}".strip(),
                   status="draft")
    session.add(reel)
    session.flush()
    reel_id = reel.id

stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
base = Path(config.OUTPUT_DIR) / f"reel_{reel_id}_{stamp}"
tts = get_tts().synthesize(script.full_text, base.with_suffix(".mp3"))
broll = PexelsBroll()
min_len = max(2.0, tts.duration / max(len(script.segments), 1))
clips = [broll.fetch(seg.broll_query, min_len) for seg in script.segments]
video_path = render_reel(script, tts, clips, base.with_suffix(".mp4"), pick_music())

with session_scope() as session:
    row = session.get(ReelRow, reel_id)
    row.audio_path = tts.audio_path
    row.video_path = str(video_path)
    row.status = "pending_review"
    cap = row.caption

logger.info(f"Wochenausblick-Reel #{reel_id} fertig: {video_path}")
print("NEWID:", reel_id)
print("VIDEO:", video_path)
print("---CAPTION---")
print(cap)
print("---END---")

import asyncio  # noqa: E402
from src.review.telegram_bot import review_configured, send_for_review  # noqa: E402
if review_configured():
    asyncio.run(send_for_review(reel_id, str(video_path), cap))
    print("sent reel", reel_id, "to Telegram review")
