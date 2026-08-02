"""One-off: build a summer-seasonality ice-cream stock reel (Unilever = Langnese/Magnum)
and send it to Telegram review. Posting happens later via the 14:00 job, gated on approval."""
import asyncio

from loguru import logger

from src.stocks.stock_reel import build_stock_reel
from src.storage.database import ReelRow, session_scope

TICKER = "UL"  # Unilever ADR (NYSE) — owns Langnese (DE), Magnum, Ben & Jerry's; reliable yfinance data
TOPIC = (
    "Traumwetter und Hitze in Deutschland — Eis-Hochsaison. Langnese und Magnum gehören zu Unilever. "
    "Aufhänger: Wie saisonal ist die Unilever-Aktie im Sommer wirklich? Überraschung: Als Basiskonsum-Riese "
    "ist Unilever kaum vom Eis-Sommer abhängig — Eis ist nur ein kleiner Teil des Konzerns, und Unilever "
    "spaltet sein Eisgeschäft 2026 gerade ab. Steige mit dem Sommer/Eis-Bild ein, liefere dann den ehrlichen "
    "Blick auf Charttechnik und Fundamentaldaten und ein überraschendes Fazit zur Saisonalität."
)

reel_id = build_stock_reel(
    TICKER, topic=TOPIC,
    hook_query="ice cream cone sunny summer",
    cta_query="happy people summer sunshine",
)
print("REEL_ID:", reel_id)
if reel_id is None:
    raise SystemExit("build failed")

# Guarantee the reach hashtags the user asked for (#sommer #sonne #eis).
with session_scope() as s:
    row = s.get(ReelRow, reel_id)
    cap = row.caption or ""
    missing = [t for t in ("#sommer", "#sonne", "#eis") if t.lower() not in cap.lower()]
    if missing:
        row.caption = cap.rstrip() + "\n" + " ".join(missing)
    video_path, final_caption = row.video_path, row.caption

print("VIDEO:", video_path)
print("---CAPTION---")
print(final_caption)
print("---END CAPTION---")

from src.review.telegram_bot import review_configured, send_for_review  # noqa: E402

if review_configured():
    asyncio.run(send_for_review(reel_id, video_path, final_caption))
    print("sent reel", reel_id, "to Telegram review")
else:
    print("telegram not configured — reel stays pending_review in DB")
