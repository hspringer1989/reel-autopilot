from src.review.telegram_bot import apply_decision
from src.storage.database import ReelRow, session_scope


def _make_reel(status="pending_review") -> int:
    with session_scope() as session:
        reel = ReelRow(trend_id=1, status=status)
        session.add(reel)
        session.flush()
        return reel.id


def _status(reel_id) -> str:
    with session_scope() as session:
        return session.get(ReelRow, reel_id).status


def test_approve_sets_status():
    reel_id = _make_reel()
    assert apply_decision(reel_id, "approve")
    assert _status(reel_id) == "approved"


def test_reject_and_regenerate():
    a, b = _make_reel(), _make_reel()
    apply_decision(a, "reject")
    apply_decision(b, "regen")
    assert _status(a) == "rejected"
    assert _status(b) == "regenerate"


def test_double_decision_is_refused():
    reel_id = _make_reel()
    apply_decision(reel_id, "approve")
    ack = apply_decision(reel_id, "reject")
    assert "bereits" in ack
    assert _status(reel_id) == "approved"


def test_unknown_action_and_missing_reel():
    assert apply_decision(_make_reel(), "explode") is None
    assert apply_decision(99999, "approve") is None


# ── Week-plan buttons (Redaktionssitzung) ──────────────────────────────────
class _FakeMessage:
    """A plain text message (no caption) — `_finish_callback` edits its text."""
    caption = None
    text = "Plan"


class _FakeQuery:
    """Minimal stand-in for a Telegram CallbackQuery."""

    def __init__(self):
        self.notes: list[str] = []
        self.message = _FakeMessage()

    async def edit_message_text(self, text, reply_markup=None):
        self.notes.append(text)


async def _noop_text(_text: str) -> None:
    return None


async def test_plan_approve_spawns_the_build(monkeypatch):
    import asyncio

    from src.feedposts import editorial
    from src.review import telegram_bot

    built: list[int] = []

    async def _fake_build(plan_id):
        built.append(plan_id)
        return [1, 2]
    monkeypatch.setattr(editorial, "build_approved_plan", _fake_build)
    monkeypatch.setattr(telegram_bot, "send_text", _noop_text)

    plan_id = editorial.save_plan([{"slug": "s", "title": "T", "brief": "b"}])
    query = _FakeQuery()
    await telegram_bot._handle_plan_callback(query, "approve", plan_id)

    assert "Freigegeben" in query.notes[0]
    await asyncio.gather(*telegram_bot._BACKGROUND)
    assert built == [plan_id]


async def test_plan_reject_blocks_generation():
    from src.feedposts import editorial
    from src.review import telegram_bot

    plan_id = editorial.save_plan([{"slug": "s", "title": "T", "brief": "b"}])
    query = _FakeQuery()
    await telegram_bot._handle_plan_callback(query, "reject", plan_id)
    assert editorial.get_plan(plan_id)["status"] == "rejected"

    await telegram_bot._handle_plan_callback(query, "approve", plan_id)   # second press
    assert "bereits" in query.notes[-1]


async def test_empty_plan_is_not_buildable():
    from src.feedposts import editorial
    from src.review import telegram_bot

    plan_id = editorial.save_plan([])
    query = _FakeQuery()
    await telegram_bot._handle_plan_callback(query, "approve", plan_id)
    assert "Keine Themen" in query.notes[-1]
    assert editorial.get_plan(plan_id)["status"] == "pending_review"
