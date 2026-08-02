"""Weekly 'Website-Hinweis' story: one fixed, always-identical card that points
viewers to the analysis archive behind the link in bio. Posted every Friday 20:00 by
the scheduler and on demand via `main.py biohint`.
The card is a finished static template (channels/<channel>/assets/templates/,
filename from PROFILE.BIO_HINT_TEMPLATE) — nothing is rendered dynamically, so every
week's story is identical."""
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

import config
from src.storage.database import StoryRow, session_scope

async def post_bio_hint_story() -> str | None:
    """Post the fixed website-hint story card. Returns the IG media id (or None)."""
    from src.publish.instagram import publish_story

    if not config.ENABLE_BIO_HINT:
        logger.info("Bio-Hinweis-Story ist für diesen Kanal deaktiviert (ENABLE_BIO_HINT)")
        return None
    template = getattr(config.PROFILE, "BIO_HINT_TEMPLATE", "story-bio-hinweis.jpg")
    img = config.CHANNEL_DIR / "assets" / "templates" / template
    if not Path(img).exists():
        logger.warning(f"Bio-Hinweis-Template fehlt: {img}")
        return None
    media_id = await publish_story(str(img))
    with session_scope() as session:
        session.add(StoryRow(
            kind="bio_hint", image_path=str(img),
            caption="Website-Hinweis (Link in Bio)",
            trade_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            status="published", ig_media_id=media_id,
            published_at=datetime.now(timezone.utc).isoformat(),
        ))
    logger.info(f"Website-Hinweis-Story gepostet: IG media id {media_id}")
    return media_id
