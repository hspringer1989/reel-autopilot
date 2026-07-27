"""Article extraction + source fact-check — both offline, no network."""
import json

from src.content.article import extract_text, looks_like_interstitial
from src.content.factcheck import check_script
from src.content.llm import FakeLLM
from src.models import ReelScript, ScriptSegment

_BODY = ("Sicherheitsforscher haben eine Lücke in der Telematik-Schnittstelle gefunden. "
         "Betroffen sind nach Angaben des Herstellers rund 40.000 Fahrzeuge eines "
         "einzigen Modelljahrgangs. Ein Angreifer konnte den Standort abfragen. "
         "Das Entriegeln der Türen war nicht möglich. Ein Update wurde ausgeliefert. ") * 3

_PAGE = f"""<html><head><title>T</title><style>.x{{color:red}}</style></head>
<body><nav>Menü Startseite Kontakt</nav><article><p>{_BODY}</p></article>
<footer>Impressum Datenschutz</footer><script>track()</script></body></html>"""


def _script():
    return ReelScript(
        hook="h",
        segments=[
            ScriptSegment(text="Eine Lücke in der Telematik-Schnittstelle wurde gefunden.", broll_query="x"),
            ScriptSegment(text="Angreifer konnten die Türen entriegeln.", broll_query="y"),
        ],
        caption="c", hashtags=["#t"],
    )


def test_extract_text_keeps_body_and_drops_chrome():
    text = extract_text(_PAGE)
    assert "Telematik-Schnittstelle" in text
    # Navigation, Fußzeile und Skripte gehören nicht zur Faktengrundlage
    assert "Impressum" not in text
    assert "track()" not in text
    assert "Menü" not in text


def test_extract_text_returns_none_for_thin_pages():
    """Ein Cookie-Banner oder eine Paywall-Hülle ist keine Quelle — lieber None als
    ein paar Wörter, die dann als 'Faktengrundlage' durchgereicht würden."""
    assert extract_text("<html><body><p>Bitte Cookies akzeptieren.</p></body></html>") is None


def test_consent_wall_is_rejected():
    """Google-News-Links landen auf consent.google.com. Die Seite liefert über 1000
    Zeichen — nur eben Cookie-Text. Genau daran ist ein Reel entstanden, das Details
    erfand, die in keinem Artikel standen."""
    wall = ("Sign in Before you continue to Google We use cookies and data to deliver "
            "and maintain Google services and to measure audience engagement. " * 6)
    assert looks_like_interstitial(wall)
    assert not looks_like_interstitial(_BODY)


def test_factcheck_reports_unsupported_segment():
    llm = FakeLLM({"fact_check": json.dumps([
        {"i": 1, "claim": "Angreifer konnten die Türen entriegeln",
         "why": "Der Artikel sagt ausdrücklich, dass das nicht möglich war"},
    ])})
    findings = check_script(_script(), _BODY, llm)
    assert len(findings) == 1
    assert "Segment 2" in findings[0]          # 0-basierter Index → 1-basierte Anzeige
    assert "entriegeln" in findings[0]


def test_factcheck_silent_when_all_covered():
    assert check_script(_script(), _BODY, FakeLLM({"fact_check": "[]"})) == []


def test_factcheck_skipped_without_source():
    """Ohne Quelltext gibt es nichts abzugleichen — ein Abgleich gegen eine blanke
    Überschrift würde alles melden und die Warnung wertlos machen."""
    boom = FakeLLM({})          # jeder Aufruf wäre ein KeyError
    assert check_script(_script(), None, boom) == []
    assert check_script(_script(), "zu kurz", boom) == []


def test_factcheck_ignores_out_of_range_index():
    llm = FakeLLM({"fact_check": json.dumps([{"i": 99, "claim": "x", "why": "y"}])})
    assert check_script(_script(), _BODY, llm) == []
