"""Kanal-Profil-VORLAGE — Kopiervorlage für einen neuen Kanal.

So legst du einen neuen Kanal an (Beispiel "tech"):
  1. Ordner kopieren:  channels/_template/  →  channels/tech/
     (mit leerer __init__.py, siehe channels/rendite/)
  2. Alle TODO(<channel>)-Stellen unten ausfüllen (Prompts, Farben, Texte).
  3. Eigene Templates nach channels/tech/assets/templates/ legen:
     feed_bg_title.png + feed_bg_content.png (1080×1350) und ein Profilbild
     (Pfad per BRAND_AVATAR in der .env setzen, sonst wird der Default erwartet).
  4. In der .env:  CHANNEL=tech  (+ BRAND_NAME, BRAND_HANDLE, eigene Tokens,
     ENABLE_STOCKS=false / ENABLE_DIVIDEND=false für Nicht-Finanz-Kanäle).
  5. Test: pytest tests/ — tests/test_profiles.py prüft, ob dein Profil dem
     Vertrag entspricht (alle Attribute vorhanden, Platzhalter korrekt).

WICHTIG: Ein Profil darf NIEMALS `config` oder `src.*` importieren (Import-Zyklus —
config.py lädt das Profil beim Start). Nur Konstanten, keine Logik.

Als Referenz für ein vollständig ausgefülltes Profil: channels/rendite/profile.py
"""

# ── Farbpalette (Keys müssen exakt so heißen; RGB-Tupel) ───────────────────
# Die Keys stammen historisch vom blauen Rendite-Design; für andere Markenfarben
# einfach andere RGB-Werte einsetzen (BLUE = Primär-Akzent, BG = Hintergrund, …).
PALETTE = {
    "BLUE": (35, 134, 209),        # TODO(<channel>): Primär-Akzent (Header, Badges, Linien)
    "BLUE_LIGHT": (125, 185, 232),  # TODO(<channel>): Sekundär-Akzent
    "BLUE_DEEP": (6, 74, 126),      # TODO(<channel>): dunkler Akzent
    "BG": (12, 36, 64),            # TODO(<channel>): dunkler Hintergrund
    "CARD": (24, 54, 90),          # TODO(<channel>): leicht abgehobene Panel-Farbe
    "FG": (238, 242, 245),         # Textfarbe hell
    "MUTED": (150, 165, 175),      # Textfarbe gedämpft
}

# ── Disclaimer ─────────────────────────────────────────────────────────────
# Für Nicht-Finanz-Kanäle reicht meist ein schlichter Bildungs-Hinweis; bei
# Werbung/Affiliate-Links bleibt die "Werbung"-Kennzeichnung Pflicht.
REEL_DISCLAIMER = "TODO(<channel>): z. B. 'Nur Bildung & Unterhaltung.'"
FEED_DISCLAIMER = "TODO(<channel>): z. B. 'Nur Bildung & Unterhaltung · Werbung'"
CARD_FOOTER_DISCLAIMER = "TODO(<channel>)"
MILESTONE_FOOTER = "TODO(<channel>): z. B. 'Danke fürs Dabeisein'"
# Lowercase-Substring: fehlt er in einer generierten Caption, hängt der Code den
# Disclaimer automatisch an. Muss im REEL_DISCLAIMER/FEED_DISCLAIMER vorkommen!
DISCLAIMER_CHECK = "TODO(<channel>): z. B. 'bildung'"

# ── Wortmarke / visuelle Identität ─────────────────────────────────────────
WORDMARK = "TODO(<channel>): z. B. 'TECH KANAL'"       # Brandmark auf hellen Story-Cards
PHOTO_WORDMARK = ("TODO", "TODO")                       # zwei Banner-Wörter auf Foto-Covern
MILESTONE_TAGLINE = "TODO(<channel>): Dankes-Satz mit Kanalnamen"

# ── Reel-Skript: System-Prompt (Sonnet) ────────────────────────────────────
# Pflicht-Platzhalter: {brand} (Kanalname) und {disclaimer} — werden per .format
# gefüllt. Struktur (Hook, Segmente, Aha-Moment, CTA) am besten beibehalten und
# nur Nische/Zielgruppe/Compliance-Regeln anpassen.
REEL_SYSTEM_PROMPT = """TODO(<channel>): System-Prompt für Reel-Skripte.
Zielgruppe/Nische beschreiben, Hook-Struktur wie im Rendite-Profil übernehmen.
CTA: "Folge {brand} …". Die Caption endet mit dem Disclaimer "{disclaimer}".
Antworte AUSSCHLIESSLICH mit einem gültigen JSON-Objekt, kein Fließtext, keine Markdown-Umrandung."""

# Beispiel-Hashtags im User-Template (Teil einer JSON-Zeile, Anführungszeichen beachten)
REEL_HASHTAG_HINT = '"#TODO", "#TODO", "…  (8-12 Stück, deutsch+reichweitenstark)"'

# ── Feed-Carousel: System-Prompt (Sonnet) ──────────────────────────────────
# Kein Pflicht-Platzhalter; Kanalname/Nische direkt in den Text schreiben.
FEED_SYSTEM_PROMPT = """TODO(<channel>): System-Prompt für Carousel-Beiträge
(Stil-/Compliance-Block wie im Rendite-Profil, Nische anpassen).
WICHTIG für gültiges JSON: in Textwerten KEINE doppelten Anführungszeichen (") und keine \
Zeilenumbrüche. Antworte AUSSCHLIESSLICH mit gültigem JSON, keine Markdown-Umrandung."""

# Phrasen, die ein generierter Feed-Text nie enthalten darf (lowercase; werden neutralisiert)
FEED_BANNED_PHRASES = ("TODO",)

FEED_HASHTAG_HINT = '"#TODO", "#TODO", "… 8-12 Stück, deutsch, reichweitenstark"'

# ── Redaktionssitzung (Wochenplanung) ──────────────────────────────────────
EDITORIAL_SYSTEM_PROMPT = """TODO(<channel>): Redakteurs-Prompt für Wochen-Themenvorschläge.
Verwende korrekte deutsche Umlaute. Antworte AUSSCHLIESSLICH mit gültigem JSON."""

# ── Community (Kommentare/DMs) ─────────────────────────────────────────────
# Regex (als String) für Formulierungen, die eine Auto-Antwort NIE enthalten darf —
# sie wird dann verworfen und an Telegram eskaliert. Für Nicht-Finanz-Kanäle z. B.
# leere Garantie-Versprechen; das Muster darf auch bewusst eng sein.
ADVICE_PATTERN = r"\b(TODO)\b"

# Pflicht-Platzhalter in beiden Prompts: {brand} und {handle} (per .replace gefüllt).
COMMENT_SYSTEM = """TODO(<channel>): Community-Stimme von {brand} ({handle}) für Kommentare.
Klassifikation harmless/substantive/sensitive/spam wie im Rendite-Profil übernehmen.
Antworte AUSSCHLIESSLICH mit einem gültigen JSON-Array, ein Objekt pro Kommentar,
"i" = Index aus der Liste. Kein Fließtext, keine Markdown-Umrandung."""

DM_SYSTEM = """TODO(<channel>): Community-Stimme von {brand} ({handle}) für DMs.
Antworte AUSSCHLIESSLICH mit einem gültigen JSON-Objekt:
{"class": "...", "confidence": 0.0, "reply": "..."}. Kein Fließtext, keine Markdown-Umrandung."""

# Pflicht-Platzhalter: {brand}
DIGEST_SYSTEM_PROMPT = """TODO(<channel>): Kommentar-Vorschläge für fremde Beiträge ({brand}).
Antworte AUSSCHLIESSLICH als JSON-Array: [{"i": 0, "comment": "…"}]."""

# Fallback-Antworten ohne LLM (nur als Vorschlag in Telegram, nie auto-gesendet).
# Die Keys "spam" und "default" sind Pflicht; weitere Keys frei wählbar, solange
# sie in FALLBACK_KEYWORDS referenziert werden.
TEMPLATE_FALLBACKS = {
    "dank": "TODO(<channel>)",
    "frage": "TODO(<channel>)",
    "spam": "",
    "default": "TODO(<channel>)",
}

# Reihenfolge zählt: erster Treffer gewinnt (Substring-Match, lowercase).
FALLBACK_KEYWORDS = (
    ("dank", ("danke", "super", "top")),
    ("frage", ("?", "wie", "was", "warum")),
)

# ── Feed-Themen-Seed (einmalig in die DB gesät, slug-idempotent) ───────────
# (slug, titel, brief) — die ersten Beiträge des Kanals.
FEED_TOPIC_SEED = [
    ("TODO-slug", "TODO: Titel des ersten Beitrags",
     "TODO: 1-3 Sätze inhaltliche Leitplanken für die Generierung."),
]

# ── Modul-Defaults (per .env überschreibbar) ───────────────────────────────
# Finanz-only-Module — für Nicht-Finanz-Kanäle auf False lassen.
ENABLE_STOCKS = False
ENABLE_DIVIDEND = False
