"""KI-Kennzeichnung nach EU KI-VO (AI Act) Art. 50 — verbindlich seit 02.08.2026.

Betroffen sind drei der vier Pflichtenkreise:

* Abs. 1 — wer direkt mit einem KI-System interagiert, muss das **bei der ersten
  Interaktion** erfahren. Betrifft unsere automatischen Antworten auf Kommentare und DMs.
* Abs. 4 UAbs. 1 — KI-erzeugte Audio-/Video-Inhalte, die authentisch wirken, sind
  offenzulegen. Unsere Reels tragen eine synthetische Sprecherstimme.
* Abs. 4 UAbs. 2 — KI-erzeugte Texte zu Themen von öffentlichem Interesse. Greift für
  unsere Finanzinhalte.

Nicht unsere Pflicht: die maschinenlesbare Markierung nach Abs. 2 trifft die ANBIETER
der KI-Systeme (ElevenLabs, Anthropic), nicht uns als Betreiber.

Verstöße sind mit bis zu 15 Mio. EUR bzw. 3 % des Weltumsatzes bewehrt — diese Tests
sind deshalb Compliance-Absicherung, keine Kosmetik.
"""
import config
from src.community.comments import mark_ai_reply


def test_auto_reply_carries_the_ai_marker():
    out = mark_ai_reply("Danke für deinen Kommentar!")
    assert out.startswith(config.PROFILE.AI_DISCLOSURE_CHAT)
    assert "Danke für deinen Kommentar!" in out


def test_marker_sits_at_the_very_start():
    """Art. 50 Abs. 1 verlangt den Hinweis bei der ERSTEN Interaktion — ein Nachsatz
    am Ende einer langen Antwort erfüllt das nicht zuverlässig."""
    out = mark_ai_reply("Zeile eins\nZeile zwei\nZeile drei")
    assert out.splitlines()[0] == config.PROFILE.AI_DISCLOSURE_CHAT


def test_marking_is_idempotent():
    """Doppelt markierte Antworten sähen aus wie ein Bug und kosten Zeichen."""
    once = mark_ai_reply("Hallo")
    assert mark_ai_reply(once) == once


def test_reel_caption_gets_the_ai_disclosure(monkeypatch):
    """Reels haben eine synthetische Stimme -> Offenlegung nach Abs. 4 UAbs. 1."""
    from src.content import script_agent

    caption = _build_caption(monkeypatch, script_agent)
    assert config.PROFILE.AI_DISCLOSURE_CHECK in caption.lower()


def test_reel_disclosure_is_not_duplicated(monkeypatch):
    """Enthält das Modell den Hinweis schon, darf er nicht ein zweites Mal erscheinen."""
    from src.content import script_agent

    caption = _build_caption(monkeypatch, script_agent,
                             caption=f"Text\n\n{config.PROFILE.AI_DISCLOSURE_CAPTION}")
    assert caption.lower().count(config.PROFILE.AI_DISCLOSURE_CHECK) == 1


def test_story_card_footer_names_the_ai(monkeypatch):
    """Story-Cards backen allen Text ins Bild — der Hinweis muss mit hinein, weil eine
    Story keine Caption hat, die der Betrachter lesen könnte."""
    from src.stocks.story_cards import footer_text

    assert config.PROFILE.AI_DISCLOSURE_FOOTER in footer_text()
    assert config.PROFILE.CARD_FOOTER_DISCLAIMER in footer_text()


def test_feed_cta_slide_names_the_ai():
    from src.feedposts import renderer

    assert config.PROFILE.AI_DISCLOSURE_FOOTER in renderer._CTA_DISCLAIMER


def test_website_footer_names_the_ai():
    assert "ki-hinweis" in config.PROFILE.SITE_FOOTER_DISCLAIMER.lower()


def _build_caption(monkeypatch, script_agent, caption: str = "Ein Text ohne Hinweise"):
    """Run the caption post-processing with a stubbed model response."""
    import json

    from src.models import TrendItem

    payload = {
        "hook": "Hook",
        "segments": [{"text": "Erstes Segment", "broll_query": "x"},
                     {"text": "Zweites Segment", "broll_query": "y"}],
        "caption": caption, "hashtags": ["#a"], "title": "T",
    }

    class _LLM:
        def complete(self, system, user, **kw):
            return json.dumps(payload)

    trend = TrendItem(source="rss", title="T", summary="S", url="")
    return script_agent.generate_script(trend, llm=_LLM()).caption
