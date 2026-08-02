"""Pexels stock-footage client: one portrait clip per script segment,
cached on disk. Returns None per segment when nothing usable is found —
the renderer then falls back to an animated gradient background."""
import json
from pathlib import Path

import httpx
from loguru import logger

import config

_SEARCH_URL = "https://api.pexels.com/videos/search"


def _pick_file(video: dict) -> dict | None:
    """Best portrait file: HD-ish, smallest that still covers 1080×1920."""
    candidates = [
        f for f in video.get("video_files", [])
        if f.get("height") and f.get("width") and f["height"] > f["width"] and f["height"] >= 1280
    ]
    return min(candidates, key=lambda f: f["height"], default=None)


class PexelsBroll:
    def __init__(self):
        self.cache_dir = Path(config.BROLL_CACHE_DIR)
        # Registry of already-used Pexels video ids so no clip repeats across reels.
        self._used_path = self.cache_dir / "used_broll.json"

    def _used(self) -> set[int]:
        try:
            return set(json.loads(self._used_path.read_text()))
        except Exception:  # noqa: BLE001 — missing/corrupt registry = start fresh
            return set()

    def _mark_used(self, vid: int) -> None:
        used = self._used()
        used.add(int(vid))
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self._used_path.write_text(json.dumps(sorted(used)))
        except Exception:  # noqa: BLE001
            pass

    def _download(self, video: dict, query: str) -> str | None:
        file = _pick_file(video)
        if not file:
            return None
        target = self.cache_dir / f"pexels_{video['id']}_{file['height']}.mp4"
        if target.exists():
            return str(target)
        try:
            data = httpx.get(file["link"], timeout=120.0, follow_redirects=True)
            data.raise_for_status()
            target.write_bytes(data.content)
            logger.info(f"B-Roll geladen: '{query}' → {target.name}")
            return str(target)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"B-Roll-Download fehlgeschlagen ({file['link']}): {exc}")
            return None

    def fetch(self, query: str, min_seconds: float) -> str | None:
        if not config.PEXELS_API_KEY or not query:
            return None
        try:
            response = httpx.get(
                _SEARCH_URL,
                headers={"Authorization": config.PEXELS_API_KEY},
                params={
                    "query": query,
                    "orientation": "portrait",
                    "size": "medium",
                    "per_page": 20,
                },
                timeout=30.0,
            )
            response.raise_for_status()
            videos = response.json().get("videos", [])
        except Exception as exc:  # noqa: BLE001 — b-roll is optional, gradient fallback exists
            logger.warning(f"Pexels-Suche '{query}' fehlgeschlagen: {exc}")
            return None

        usable = [v for v in videos if v.get("duration", 0) >= min_seconds and _pick_file(v)]
        used = self._used()
        # 1) prefer a clip we have never used → variety across reels
        for video in usable:
            if int(video.get("id", 0)) in used:
                continue
            path = self._download(video, query)
            if path:
                self._mark_used(video["id"])
                return path
        # 2) all matches already used → reuse the first usable (better than a blank gradient)
        if usable:
            logger.info(f"B-Roll '{query}': alle {len(usable)} Treffer schon verwendet — wiederverwende")
            return self._download(usable[0], query)
        return None
