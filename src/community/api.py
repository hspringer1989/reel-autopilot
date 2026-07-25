"""Instagram Graph API client for comments + messaging, behind a port with an
offline fake (same ports-and-fakes pattern as `src/publish/instagram.py`).

Works with the Instagram-Login variant (graph.instagram.com, creator account).
Read methods return [] / None on API errors (log and continue); write methods
raise `CommunityAPIError` so the caller can mark the item 'failed' and retry later.

Endpoints (all under {GRAPH_BASE_URL}/{GRAPH_API_VERSION}, token = IG_ACCESS_TOKEN):
  GET  /{media-id}/comments      — comments on our own media
  POST /{comment-id}/replies     — reply to a comment
  POST /{comment-id}?hide=true   — hide a comment (spam)
  GET  /me/conversations         — DM threads (platform=instagram)
  POST /me/messages              — send a DM (recipient IGSID, 24h window)
  GET  /ig_hashtag_search        — hashtag id (likely UNAVAILABLE on Instagram-Login)
  GET  /{hashtag-id}/recent_media
"""
from abc import ABC, abstractmethod

import httpx
from loguru import logger

import config

_TIMEOUT_S = 30.0


class CommunityAPIError(RuntimeError):
    """Raised by write operations (reply/send/hide) when the API rejects the call."""


class CommunityAPI(ABC):
    """Port: normalised, provider-agnostic access to comments + messaging.

    Normalised shapes returned:
      comment  = {id, text, username, from_id, timestamp, parent_id}
      thread   = {id, participant_id, participant_username, updated_time,
                  messages: [{id, from_id, text, created_time, attachment_type}]}
      media    = {id, permalink, caption}
    """

    @abstractmethod
    async def fetch_comments(self, media_id: str) -> list[dict]: ...

    @abstractmethod
    async def reply_to_comment(self, comment_id: str, message: str) -> str: ...

    @abstractmethod
    async def hide_comment(self, comment_id: str, hide: bool = True) -> bool: ...

    @abstractmethod
    async def fetch_conversations(self) -> list[dict]: ...

    @abstractmethod
    async def send_dm(self, recipient_id: str, text: str) -> str: ...

    @abstractmethod
    async def find_hashtag_id(self, name: str) -> str | None: ...

    @abstractmethod
    async def hashtag_recent_media(self, hashtag_id: str) -> list[dict]: ...

    @abstractmethod
    async def probe(self) -> dict: ...


def _base() -> str:
    return f"{config.GRAPH_BASE_URL}/{config.GRAPH_API_VERSION}"


def _normalise_comment(raw: dict) -> dict:
    frm = raw.get("from") or {}
    return {
        "id": str(raw.get("id", "")),
        "text": raw.get("text", "") or "",
        "username": raw.get("username", "") or frm.get("username", ""),
        "from_id": str(frm.get("id", "")),
        "timestamp": raw.get("timestamp", ""),
        "parent_id": str(raw.get("parent_id", "")),
    }


class GraphCommunityAPI(CommunityAPI):
    def __init__(self) -> None:
        self._token = {"access_token": config.IG_ACCESS_TOKEN}

    async def fetch_comments(self, media_id: str) -> list[dict]:
        params = {"fields": "id,text,username,from,timestamp,parent_id", **self._token}
        async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
            body = (await client.get(f"{_base()}/{media_id}/comments", params=params)).json()
        if "data" not in body:
            err = body.get("error", {})
            # A media object that no longer exists (user deleted the post) or has no
            # comments edge returns code 100 / subcode 33 — expected, log at debug so a
            # single stale id does not spam a warning every poll cycle. Real errors warn.
            if err.get("code") == 100 and err.get("error_subcode") == 33:
                logger.debug(f"Kommentare für {media_id} nicht verfügbar (Medium gelöscht/ohne Kommentar-Objekt)")
            else:
                logger.warning(f"Kommentare für {media_id} nicht abrufbar: {err or body}")
            return []
        return [_normalise_comment(c) for c in body["data"]]

    async def reply_to_comment(self, comment_id: str, message: str) -> str:
        async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
            body = (await client.post(
                f"{_base()}/{comment_id}/replies",
                data={"message": message[:2200], **self._token},
            )).json()
        if "id" not in body:
            raise CommunityAPIError(f"Antwort auf Kommentar {comment_id} fehlgeschlagen: {body}")
        return str(body["id"])

    async def hide_comment(self, comment_id: str, hide: bool = True) -> bool:
        async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
            body = (await client.post(
                f"{_base()}/{comment_id}",
                data={"hide": "true" if hide else "false", **self._token},
            )).json()
        if body.get("success") is True or body.get("id"):
            return True
        logger.warning(f"Kommentar {comment_id} verbergen fehlgeschlagen: {body.get('error', body)}")
        return False

    async def fetch_conversations(self) -> list[dict]:
        # One nested call gets threads + their messages; only recent messages matter.
        fields = ("id,updated_time,participants,"
                  "messages{id,from,message,created_time,attachments}")
        params = {"platform": "instagram", "fields": fields, **self._token}
        async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
            body = (await client.get(f"{_base()}/me/conversations", params=params)).json()
        if "data" not in body:
            logger.warning(f"Conversations nicht abrufbar: {body.get('error', body)}")
            return []
        threads: list[dict] = []
        for conv in body["data"]:
            parts = (conv.get("participants") or {}).get("data") or []
            other = next((p for p in parts if str(p.get("id")) != str(config.IG_USER_ID)), {})
            msgs = []
            for m in (conv.get("messages") or {}).get("data") or []:
                frm = m.get("from") or {}
                atts = (m.get("attachments") or {}).get("data") or []
                msgs.append({
                    "id": str(m.get("id", "")),
                    "from_id": str(frm.get("id", "")),
                    "text": m.get("message", "") or "",
                    "created_time": m.get("created_time", ""),
                    "attachment_type": (atts[0].get("type", "") if atts else ""),
                })
            threads.append({
                "id": str(conv.get("id", "")),
                "participant_id": str(other.get("id", "")),
                "participant_username": other.get("username", ""),
                "updated_time": conv.get("updated_time", ""),
                "messages": msgs,
            })
        return threads

    async def send_dm(self, recipient_id: str, text: str) -> str:
        import json

        payload = {
            "recipient": json.dumps({"id": recipient_id}),
            "message": json.dumps({"text": text[:1000]}),
            **self._token,
        }
        async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
            body = (await client.post(f"{_base()}/me/messages", data=payload)).json()
        mid = body.get("message_id") or body.get("id")
        if not mid:
            raise CommunityAPIError(f"DM an {recipient_id} fehlgeschlagen: {body}")
        return str(mid)

    async def find_hashtag_id(self, name: str) -> str | None:
        params = {"user_id": config.IG_USER_ID, "q": name, **self._token}
        async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
            body = (await client.get(f"{_base()}/ig_hashtag_search", params=params)).json()
        data = body.get("data")
        if not data:
            logger.info(f"Hashtag-Suche '{name}' nicht verfügbar/leer: {body.get('error', body)}")
            return None
        return str(data[0].get("id", "")) or None

    async def hashtag_recent_media(self, hashtag_id: str) -> list[dict]:
        params = {
            "user_id": config.IG_USER_ID,
            "fields": "id,permalink,caption",
            **self._token,
        }
        async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
            body = (await client.get(
                f"{_base()}/{hashtag_id}/recent_media", params=params
            )).json()
        if "data" not in body:
            return []
        return [
            {"id": str(m.get("id", "")), "permalink": m.get("permalink", ""),
             "caption": m.get("caption", "") or ""}
            for m in body["data"]
        ]

    async def probe(self) -> dict:
        """Read-only capability check used by `verify-ig`: which community edges work?"""
        result = {"comments": None, "messaging": None, "hashtag_search": None}
        token = self._token
        async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
            conv = (await client.get(
                f"{_base()}/me/conversations",
                params={"platform": "instagram", "limit": 1, **token},
            )).json()
            result["messaging"] = "error" not in conv
            hs = (await client.get(
                f"{_base()}/ig_hashtag_search",
                params={"user_id": config.IG_USER_ID, "q": "finanzen", **token},
            )).json()
            result["hashtag_search"] = "data" in hs
        return result


class FakeCommunityAPI(CommunityAPI):
    """Offline stand-in: canned comments/threads, records every outbound call so
    tests can assert what would have been posted."""

    def __init__(
        self,
        comments: dict[str, list[dict]] | None = None,
        threads: list[dict] | None = None,
        hashtag_media: dict[str, list[dict]] | None = None,
        hashtag_available: bool = False,
    ) -> None:
        self._comments = comments or {}
        self._threads = threads or []
        self._hashtag_media = hashtag_media or {}
        self._hashtag_available = hashtag_available
        self.replied: list[tuple[str, str]] = []   # (comment_id, message)
        self.hidden: list[str] = []
        self.sent_dms: list[tuple[str, str]] = []   # (recipient_id, text)

    async def fetch_comments(self, media_id: str) -> list[dict]:
        return [_normalise_comment(c) for c in self._comments.get(media_id, [])]

    async def reply_to_comment(self, comment_id: str, message: str) -> str:
        self.replied.append((comment_id, message))
        return f"reply_{comment_id}"

    async def hide_comment(self, comment_id: str, hide: bool = True) -> bool:
        self.hidden.append(comment_id)
        return True

    async def fetch_conversations(self) -> list[dict]:
        return list(self._threads)

    async def send_dm(self, recipient_id: str, text: str) -> str:
        self.sent_dms.append((recipient_id, text))
        return f"dm_{len(self.sent_dms)}"

    async def find_hashtag_id(self, name: str) -> str | None:
        return f"hid_{name}" if self._hashtag_available else None

    async def hashtag_recent_media(self, hashtag_id: str) -> list[dict]:
        return list(self._hashtag_media.get(hashtag_id, []))

    async def probe(self) -> dict:
        return {"comments": True, "messaging": True,
                "hashtag_search": self._hashtag_available}


def get_api() -> CommunityAPI:
    """Fake when the whole LLM stack is faked (offline dry-runs/tests), else Graph."""
    if config.LLM_PROVIDER == "fake":
        return FakeCommunityAPI()
    return GraphCommunityAPI()
