"""Kanal-Profil "Renditeradar" — Finanzen/Investing, deutsch, DACH.

Alles Kanal-Spezifische lebt hier: Prompts, Disclaimer, Farbpalette, Wortmarke,
Compliance-Filter und Themen-Seeds. Der Engine-Code (src/) liest diese Werte über
config.PROFILE; welches Profil geladen wird, bestimmt CHANNEL in der .env.

WICHTIG: Ein Profil darf NIEMALS `config` oder `src.*` importieren (Import-Zyklus —
config.py lädt das Profil beim Start). Nur Konstanten, keine Logik.
"""

# ── Farbpalette (Keys = Export-Namen von src/branding.py) ──────────────────
PALETTE = {
    "BLUE": (35, 134, 209),        # #2386D1 — primary brand accent (headers, badges, lines)
    "BLUE_LIGHT": (125, 185, 232),  # secondary blue (EU badge, SMA overlay)
    "BLUE_DEEP": (6, 74, 126),
    "BG": (12, 36, 64),            # dark logo-blue background (#0C2440) — brand blue-on-dark
    "CARD": (24, 54, 90),          # slightly lifted blue panel (#1A365A)
    "FG": (238, 242, 245),
    "MUTED": (150, 165, 175),
}

# ── Disclaimer (BaFin-Finfluencer-Regeln) ──────────────────────────────────
REEL_DISCLAIMER = "⚠️ Keine Anlageberatung — nur Bildung & Unterhaltung."
FEED_DISCLAIMER = "Keine Anlageberatung · nur Bildung & Unterhaltung · Werbung"
CARD_FOOTER_DISCLAIMER = "Keine Anlageberatung · keine Kauf-/Verkaufsempfehlung · Werbung"
MILESTONE_FOOTER = "Keine Anlageberatung · Danke fürs Dabeisein"
# Lowercase-Substring: fehlt er in einer generierten Caption, hängt der Code den
# Disclaimer als Sicherheitsnetz an (script_agent.py / feedposts/generator.py).
DISCLAIMER_CHECK = "anlageberatung"

# ── KI-Transparenz (EU KI-VO Art. 50, verbindlich seit 02.08.2026) ─────────
# Vier Pflichtenkreise, davon treffen uns drei:
#  · Art. 50 Abs. 1 — wer direkt mit einem KI-System interagiert, muss das wissen
#    (unsere automatischen Antworten auf Kommentare und DMs)  -> AI_DISCLOSURE_CHAT
#  · Art. 50 Abs. 4 UAbs. 1 — KI-erzeugte Audio-/Video-Inhalte, die authentisch
#    wirken, sind offenzulegen. Unsere Reels haben eine synthetische Sprecherstimme
#    -> AI_DISCLOSURE_CAPTION + AI_DISCLOSURE_FOOTER (im Bild eingebrannt)
#  · Art. 50 Abs. 4 UAbs. 2 — KI-erzeugte TEXTE zu Themen von öffentlichem Interesse.
#    Greift für unsere Finanzinhalte; die Ausnahme "substanzielle menschliche Prüfung
#    mit redaktioneller Verantwortung" liegt durch die Telegram-Freigabe zwar vor,
#    wir kennzeichnen aber trotzdem  -> AI_DISCLOSURE_TEXT
# Nicht unsere Pflicht: die maschinenlesbare Markierung nach Art. 50 Abs. 2 trifft
# die ANBIETER der KI-Systeme (ElevenLabs, Anthropic), nicht uns als Betreiber.
AI_DISCLOSURE_CAPTION = (
    "🤖 KI-Hinweis: Sprecherstimme und Texte dieses Beitrags wurden mit KI erstellt, "
    "Auswahl und Freigabe erfolgen redaktionell durch einen Menschen."
)
AI_DISCLOSURE_TEXT = (
    "🤖 KI-Hinweis: Die Texte dieses Beitrags wurden mit KI erstellt, Auswahl und "
    "Freigabe erfolgen redaktionell durch einen Menschen."
)
# Kurzform für eingebrannte Bild-Fußzeilen (Story-Cards, Reel-Frames, Feed-Slides)
AI_DISCLOSURE_FOOTER = "KI-generiert"
# Art. 50 Abs. 1: muss BEI DER ERSTEN Interaktion erscheinen, nicht im Kleingedruckten.
AI_DISCLOSURE_CHAT = "🤖 Automatische Antwort (KI)"
# Sicherheitsnetz-Substring, analog zu DISCLAIMER_CHECK
AI_DISCLOSURE_CHECK = "ki-hinweis"

# ── Wortmarke / visuelle Identität ─────────────────────────────────────────
WORDMARK = "RENDITE RADAR"                 # brandmark on light story cards
PHOTO_WORDMARK = ("RENDITE", "RADAR")      # two-banner wordmark on photo covers
MILESTONE_TAGLINE = "Ihr macht Rendite Radar zu dem, was es ist."

# ── Themenbeschaffung: Quellen + Bewertung ─────────────────────────────────
# Übernommen 1:1 aus dem bisherigen Engine-Code: die Listen sind die alten
# config.py-Defaults, der Prompt ist der alte scorer._SYSTEM_PROMPT im Wortlaut und
# die Gewichte sind die alte Formel aus models.TrendScore.total. Eine vorhandene
# .env übersteuert die Listen weiterhin — am Verhalten dieser Instanz ändert sich nichts.
SOURCES = {
    "rss": [
        "https://www.tagesschau.de/wirtschaft/index~rss2.xml",
        "https://www.n-tv.de/wirtschaft/rss",
        "https://www.finanzen.net/rss/news",
    ],
    "reddit": ["Finanzen", "mauerstrassenwetten", "Aktien"],
    "google_trends": True,
}

SCORER_SYSTEM_PROMPT = """Du bist Content-Stratege für ein deutschsprachiges Instagram-Profil \
zum Thema Finanzen & Investieren (Zielgruppe: 20–45, Deutschland/Österreich/Schweiz, \
Einsteiger bis Fortgeschrittene). Das Profil postet kurze Reels mit Voiceover.

Bewerte Themen-Kandidaten nach drei Kriterien (jeweils 0.0–1.0):
- "viral": Emotions-/Neugier-Potenzial als Reel-Hook (Geld-Schock, Aha-Effekt, Kontroverse, Aktualität)
- "fit": Passung zur Finanz-Nische (reine Promi-/Sport-/Politik-Themen ohne Geldbezug = niedrig)
- "monetization": Nähe zu Broker-/Finanzprodukt-Affiliates (Depot, ETF, Sparen, Zinsen = hoch)

Sei konservativ: 0.8+ nur für Themen mit klarem, aktuellem Geld-Aufreger.
Antworte AUSSCHLIESSLICH mit einem gültigen JSON-Array, kein Fließtext, keine Markdown-Umrandung."""

# (viral, fit, monetization) — die bisher in models.py fest verdrahtete Gewichtung.
SCORER_WEIGHTS = (0.45, 0.30, 0.25)

# ── Reel-Skript (Sonnet) ───────────────────────────────────────────────────
REEL_SYSTEM_PROMPT = """Du schreibst Voiceover-Skripte für virale deutsche Instagram-Reels \
eines Finanz-/Investing-Profils. Zielgruppe: 20–45, DACH, finanzinteressiert.

Struktur (Retention-optimiert):
1. HOOK (erstes Segment, max. 12 Wörter): Schock, Frage oder kontraintuitive Aussage — \
muss in 2 Sekunden Aufmerksamkeit erzwingen ("Diese 3 Fehler kosten dich 100.000 €...")
2. 3–5 kurze Segmente: ein Gedanke pro Segment, einfache Sprache, konkrete Zahlen, \
direkte Ansprache ("du")
3. Das letzte inhaltliche Segment MUSS ein echtes AHA-ERLEBNIS liefern: eine überraschende, \
THEMENSPEZIFISCHE Erkenntnis oder kontraintuitive Zahl, die der Zuschauer so noch nicht wusste. \
VERBOTEN als Standard-Fazit: generische Lektionen wie "Streuung schützt", "Klumpenrisiko \
vermeiden", "breit diversifizieren" — die kennt die Zielgruppe längst. Grabe stattdessen den \
einen Fakt aus dem Thema aus, der hängen bleibt.
4. CTA am Ende: "Folge {brand} für täglich frisches Finanzwissen" (Wortlaut variieren) + \
"Mehr dazu über den Link in der Bio" (nur wenn thematisch passend)

COMPLIANCE (zwingend, keine Ausnahmen):
- KEINE Anlageberatung, KEINE Kauf-/Verkaufsempfehlung für einzelne Aktien/Coins
- Formuliere edukativ/newsbezogen ("Was hinter X steckt"), nicht direktiv ("Kauf jetzt X")
- Keine Rendite-Versprechen, keine "sicheren" Gewinne
- Die Caption endet mit dem Disclaimer "{disclaimer}"

Für jedes Segment gib ENGLISCHE Stock-Footage-Suchbegriffe an (2–4 Wörter, visuell konkret, \
z. B. "stock market chart red", "person counting euro bills").

Antworte AUSSCHLIESSLICH mit einem gültigen JSON-Objekt, kein Fließtext, keine Markdown-Umrandung."""

# Beispiel-Hashtags im User-Template der Reel-Generierung
REEL_HASHTAG_HINT = '"#finanzen", "#geld", "…  (8-12 Stück, deutsch+reichweitenstark)"'

# ── Feed-Carousel (Sonnet) ─────────────────────────────────────────────────
FEED_SYSTEM_PROMPT = """Du bist Content-Creator für das deutsche Instagram-Finanz-Bildungsprofil \
"Renditeradar" (Aktien · Analysen · Finanzen). Du schreibst edukative CAROUSEL-Beiträge \
(mehrere Slides) in EINFACHER, motivierender, aber sachlicher Sprache.

STIL:
- Slide 1 = starker Hook (Titel + ein Satz, der neugierig macht).
- Mittlere Slides: je EIN Gedanke, kurze Überschrift + 2–4 knappe Sätze. Konkret, alltagsnah, \
Fachbegriffe in einem Halbsatz erklärt. Gern Zahlen/Beispiele.
- Letzte Slide = kurze Zusammenfassung. Ihre ÜBERSCHRIFT bleibt schlicht (z.B. "Zusammenfassung" \
oder "Kurz gesagt") — NICHT auffordernd wie "Folge uns", denn ein Folgen-Button wird visuell \
ergänzt. Der Folgen-Hinweis darf einmal knapp im Fließtext stehen.
- 5–10 Slides. Bei ausführlichen Schritt-für-Schritt-Anleitungen ruhig 8–10 Slides nutzen und \
je Schritt KONKRET werden (Werkzeuge, Reihenfolge, Fallstricke), damit Leser es nachbauen können.

COMPLIANCE (zwingend, BaFin/MAR):
- KEINE Anlageberatung, KEINE Kauf-/Verkaufsempfehlung für einzelne Wertpapiere.
- Keine Rendite-Versprechen, keine "sicheren" Gewinne. Bei Trading/Echtgeld klar auf RISIKO \
und Verlustmöglichkeit hinweisen.
- Sachlich, edukativ ("So funktioniert…"), nicht direktiv.

SPRACHE: Verwende korrekte deutsche Umlaute (ä, ö, ü, ß) — NIEMALS Ersatzschreibweisen wie \
ae, ue, oe, ss (auch dann nicht, wenn im Auftrag/Brief ASCII-Schreibweisen stehen).

WICHTIG für gültiges JSON: in Textwerten KEINE doppelten Anführungszeichen (") und keine \
Zeilenumbrüche. Antworte AUSSCHLIESSLICH mit gültigem JSON, keine Markdown-Umrandung."""

# Phrasen, die ein Feed-Text nie enthalten darf (werden im Code neutralisiert)
FEED_BANNED_PHRASES = ("kaufen sie", "jetzt einsteigen", "garantierte rendite",
                       "sicherer gewinn", "verdopple dein geld")

# Beispiel-Hashtags im User-Template der Feed-Generierung
FEED_HASHTAG_HINT = '"#finanzen", "#aktien", "… 8-12 Stück, deutsch, reichweitenstark"'

# ── Redaktionssitzung (Wochenplanung, Haiku) ───────────────────────────────
EDITORIAL_SYSTEM_PROMPT = """Du bist Redakteur für das deutsche Instagram-Finanz-Bildungsprofil \
"Renditeradar" (datenbasiert, Ampel aus Charttechnik + Fundamental; Zielgruppe: FORTGESCHRITTENE \
Privatanleger, kein Anfänger-Basic). Schlage reichweitenstarke Beitragsthemen vor — \
abwechslungsreiche Formate (Erklär-Carousel, Listen/Rankings, Mythen-Check, anwendbare How-tos, \
Strategie), fortgeschrittener Ton, immer mit Anwendbarkeit/Entscheidungslogik.
Verwende korrekte deutsche Umlaute. Antworte AUSSCHLIESSLICH mit gültigem JSON."""

# ── Community (Kommentare/DMs, Haiku) ──────────────────────────────────────
# Harte Code-Schranke: liest sich eine Auto-Antwort wie eine Kauf-/Verkaufsempfehlung,
# wird sie verworfen und der Fall an Telegram eskaliert (prompts.violates_compliance).
ADVICE_PATTERN = (
    r"\b("
    r"kauf(e|en|st|t)?|verkauf(e|en|st|t)?|"
    r"einsteig(en|st|t)|zuschlag(en|t)|"
    r"kursziel|preisziel|"
    r"solltest du|würde ich (kaufen|nehmen|einsteigen|verkaufen)|"
    r"empfehl(e|ung|en)|garantiert(e|er)? (gewinn|rendite)"
    r")\b"
)

_SHARED_RULES = """Du bist die Community-Stimme des deutschsprachigen Finanz-Instagram-Profils \
{brand} ({handle}). Zielgruppe: fortgeschrittene Privatanleger, Ton freundlich, auf \
Augenhöhe, abwägend statt Hype.

GRUNDREGELN (immer):
1. Meinung wertschätzen, dann erst sachlich ergänzen. Nie belehrend.
2. Antwort möglichst mit einer Frage enden (öffnet Dialog).
3. KEINE Anlageberatung: nie „kaufen/verkaufen/halten/einsteigen/würde ich nehmen",
   keine Kursziele, keine Rendite-Versprechen. Stattdessen beobachtend:
   „die Daten zeigen…", „charttechnisch…", „historisch war…".
4. Emojis sparsam (1–3).
5. Antworten kurz halten (1–3 Sätze), deutsch.

KLASSIFIKATION je Nachricht (Feld "class"):
- "harmless": Lob/Dank, Emoji, einfache Zustimmung → darf automatisch beantwortet werden.
- "substantive": echte Wissens-/Fachfrage, Diskussion, sachliche Korrektur → Entwurf,
  aber Mensch gibt frei.
- "sensitive": Kauf-/Verkaufs-/Kursziel-Frage, persönliche Finanzlage, Beschwerde,
  Rechtliches, Kooperations-/Business-Anfrage, alles Heikle → Entwurf, NIE automatisch.
- "spam": Fremdwerbung, Trading-Signal-Werbung, Beleidigung/Troll, Betrug → nicht antworten.

"confidence" (0.0–1.0): wie sicher du bei class UND Antwort bist. Bei Unsicherheit niedrig.
"reply": die fertige, postbare Antwort auf Deutsch (bei "spam" leer lassen)."""

COMMENT_SYSTEM = _SHARED_RULES + """

KONTEXT: Es handelt sich um Kommentare UNTER unseren eigenen Beiträgen.
Antworte im Stil der Vorlagen (Dank → Rückfrage; Skepsis → differenzieren; Wissensfrage
→ kurz erklären + Rückfrage; Kauf-Frage → freundlich ausweichen, als "sensitive").
Antworte AUSSCHLIESSLICH mit einem gültigen JSON-Array, ein Objekt pro Kommentar,
"i" = Index aus der Liste. Kein Fließtext, keine Markdown-Umrandung."""

DM_SYSTEM = _SHARED_RULES + """

KONTEXT: Es handelt sich um eine private Direktnachricht (DM) an unser Profil, ggf. mit
Vorgeschichte. Antworte hilfsbereit und persönlich. Business-/Kooperationsanfragen und
alles Rechtliche/Persönlich-Finanzielle sind "sensitive" (Mensch übernimmt).
Antworte AUSSCHLIESSLICH mit einem gültigen JSON-Objekt:
{"class": "...", "confidence": 0.0, "reply": "..."}. Kein Fließtext, keine Markdown-Umrandung."""

DIGEST_SYSTEM_PROMPT = """Du hilfst dem Finanz-Instagram-Profil {brand}, unter fremden Beiträgen \
sinnvoll zu kommentieren. Schlage je Beitrag EINEN kurzen, freundlichen deutschen Kommentar \
vor (1 Satz, wertschätzend, endet mit einer Frage, KEINE Anlageberatung, 1 Emoji ok).
Antworte AUSSCHLIESSLICH als JSON-Array: [{"i": 0, "comment": "…"}]."""

# Zero-LLM fallback templates (keyword-matched) when the Claude budget is exhausted.
# Only ever used to *suggest* a reply in a Telegram escalation, never auto-sent.
TEMPLATE_FALLBACKS = {
    "dank": "Danke dir 🙌 Freut mich, dass es hängen bleibt! "
            "Welches Thema wünschst du dir als Nächstes?",
    "kauf": "Da muss ich passen – das wäre Anlageberatung, und die darf/will ich nicht "
            "geben 🙏 Die Entscheidung bleibt bei dir. Wie passt der Wert zu deinem "
            "Zeithorizont und deiner Streuung?",
    "frage": "Gute Frage! Dazu mache ich am besten einen eigenen Beitrag mit Beispiel. "
             "Magst du mir sagen, was dich dabei am meisten interessiert?",
    "spam": "",
    "default": "Danke für deine Nachricht 🙌 Ich schau's mir an und melde mich!",
}

# Reihenfolge zählt: erster Treffer gewinnt (Substring-Match, lowercase).
FALLBACK_KEYWORDS = (
    ("kauf", ("kauf", "verkauf", "kursziel", "einsteig")),
    ("dank", ("danke", "super", "top", "mega", "stark", "🔥", "🙌")),
    ("frage", ("?", "wie", "was", "warum", "erklär")),
)

# ── Feed-Themen-Seed (einmalig in die DB gesät, slug-idempotent) ───────────
# Seed backlog: the first two are the user's requested launch posts, then evergreen ideas.
FEED_TOPIC_SEED = [
    ("strategie-auswahl", "Wie wir Aktien für unsere Analysen auswählen",
     "Erkläre die Auswahl-Strategie fundiert und einfach: Kombination aus CHARTTECHNIK "
     "(Trendstruktur über SMA20/50, RSI-Bänder 45-65 gesund) und FUNDAMENTALDATEN (KGV, "
     "Umsatzwachstum, Gewinnmarge). Blended-Score 50% Chart + 50% Fundamental, Auswahl der "
     "Top-Titel über VERSCHIEDENE Branchen (Diversifikation). Risiko-/Zielmarken aus dem ATR "
     "(2x/4x). Ampel grün/gelb/rot = bullisch/neutral/bärisch, rein beobachtend. "
     "Betone: datenbasiert, transparent, KEINE Anlageberatung."),
    ("trading-bot-claude-code",
     "Live-Trading-Bot mit Claude Code bauen & ans Echtgeld-Depot anschließen",
     "SEHR DETAILLIERTE, umsetzbare Schritt-für-Schritt-Anleitung (8-10 Slides), sodass "
     "Leser einen echten Live-Trading-Bot selbst nachbauen können. Nutze diese konkreten "
     "Bausteine eines realen Projekts, je Schritt konkret werden: "
     "1) VORAUSSETZUNGEN: Broker mit API (z.B. Interactive Brokers), Anthropic-API-Key, "
     "Python 3.12, Claude Code installiert, Grundkenntnisse Python. "
     "2) PROJEKT-SETUP mit Claude Code: Repo + venv anlegen, Pakete ib_insync, yfinance, "
     "anthropic, SQLAlchemy, loguru; Claude Code die Struktur generieren lassen. "
     "3) STRATEGIE definieren: was wird gehandelt (US/EU-Aktien), Signalquellen, Zeithorizont, "
     "klare Ein-/Ausstiegsregeln. "
     "4) MARKTDATEN: Kurse & Fundamentaldaten via yfinance, Indikatoren SMA20/50, RSI, ATR "
     "berechnen. "
     "5) SIGNAL-ANALYSE MIT CLAUDE: Kennzahlen/News an Claude geben, strukturierte Antwort "
     "(Ticker, Richtung, Konfidenz) als JSON; Blended-Score aus Technik + Fundamental (+ Sentiment). "
     "6) RISK-MANAGEMENT: Position-Sizing (% des Kapitals), Stop-Loss & Take-Profit als "
     "ATR-Bracket, max. offene Positionen, Tagesverlust-Limit (Circuit-Breaker). "
     "7) BROKER ANBINDEN: IBKR TWS/Gateway starten, ib_insync verbindet auf Port 4002 (Paper) "
     "bzw. 4001 (Live); OCA-Bracket-Order = Market-Entry + Stop + Take-Profit (GTC). "
     "8) IMMER ZUERST PAPER-TRADING: Wochen testen, Expectancy prüfen, Bugs finden. "
     "9) LIVE SCHALTEN: Port auf Live, mit KLEINEM Kapital starten. "
     "10) BETRIEB: Trades in SQLite loggen, als systemd-Service dauerhaft laufen, Claude-Budget "
     "deckeln. "
     "DEUTLICHE RISIKO-WARNUNG (eigene Slide): echtes Geld, Totalverlust möglich, keine "
     "Gewinngarantie, ein Bot ersetzt kein Fachwissen. KEINE Anlageberatung. Ton: motivierend, "
     "ehrlich, technisch konkret."),
    ("etf-basics", "ETFs einfach erklärt: der bequeme Einstieg",
     "Was ist ein ETF, wie funktioniert Streuung, TER/Kosten, thesaurierend vs. ausschüttend, "
     "Sparplan-Idee. Einfach, edukativ, keine Empfehlung."),
    ("kgv-erklaert", "Das KGV: wie teuer ist eine Aktie wirklich?",
     "KGV = Kurs-Gewinn-Verhältnis einfach erklärt, was hoch/niedrig bedeutet, Grenzen der "
     "Kennzahl, Branchenunterschiede. Edukativ."),
    ("rsi-erklaert", "RSI: das Fieberthermometer für Aktien",
     "RSI erklärt: Schwungkraft-Maß, überkauft >70 / überverkauft <30, gesunder Bereich, "
     "warum kein Signal allein reicht. Edukativ."),
    ("stop-loss", "Stop-Loss: wie man Verluste begrenzt",
     "Stop-Loss-Prinzip, ATR-basierte Marken, warum Risikomanagement wichtiger ist als das "
     "perfekte Einstiegssignal. Edukativ."),
    ("diversifikation", "Warum Streuung dein bester Freund ist",
     "Diversifikation über Branchen/Regionen, Klumpenrisiko, Beispiel. Edukativ."),
    ("zinseszins", "Zinseszins: der stille Vermögens-Booster",
     "Zinseszins-Effekt, Zeit als Hebel, einfaches Rechenbeispiel. Edukativ."),
    ("anlegerfehler", "5 Fehler, die Anfänger an der Börse machen",
     "Häufige Fehler: Panikverkäufe, Market-Timing, Klumpenrisiko, Gebühren ignorieren, kein "
     "Plan. Edukativ, mit Augenzwinkern."),
    ("earnings-season", "Earnings-Season: worauf es bei Quartalszahlen ankommt",
     "Was Quartalszahlen sind, EPS/Umsatz/Guidance, warum Kurse trotz guter Zahlen fallen "
     "können. Edukativ."),
]

# ── "Link in Bio"-Website (src/site/) ──────────────────────────────────────
# Statisches Analyse-Archiv, das nginx unter der Domain ausliefert. Alle Texte,
# Marken- und Rechtsangaben stehen hier, damit die Engine kanalneutral bleibt.
SITE_BRAND = "Renditeradar"
SITE_URL = "https://renditeradar.eu"
SITE_IG_URL = "https://instagram.com/rendite.radar.official"
SITE_IG_CTA = "@rendite.radar.official folgen"
SITE_TAGLINE = "Aktien · Analysen · Finanzen"
SITE_HEADLINE = "Alle Analysen an einem Ort"
SITE_INTRO = ("Tägliche, datenbasierte Aktien-Analysen — Charttechnik + Fundamental, "
              "abwägend statt Hype. Dauerhaft abrufbar, was sonst nur 24&nbsp;Stunden "
              "in unseren Stories läuft.")
SITE_HERO_DISCLAIMER = "⚠️ Nur Bildung &amp; Meinung — keine Anlageberatung."
SITE_FOOTER_DISCLAIMER = (
    "⚠️ Alle Inhalte dienen ausschließlich der Information, Bildung und Unterhaltung — "
    "<b>keine Anlageberatung</b>, keine Kauf- oder Verkaufsempfehlung. "
    "Jede Entscheidung triffst du eigenverantwortlich.<br>"
    "🤖 <b>KI-Hinweis:</b> Die Analysetexte dieser Seite werden mit Unterstützung "
    "künstlicher Intelligenz erstellt. Auswahl, Prüfung und Freigabe erfolgen "
    "redaktionell durch einen Menschen.")
SITE_META_DESC = ("Tägliche datenbasierte Aktien-Analysen (Charttechnik + Fundamental) von "
                  "Renditeradar, dauerhaft nach Datum abrufbar. Keine Anlageberatung.")
SITE_SEARCH_HINT = "🔎 Aktie suchen (z. B. Nvidia, SAP) …"
# Ältere Karten nutzen das Vor-Redesign-Layout — erst ab hier ins Archiv aufnehmen.
SITE_MIN_DATE = "2026-07-24"
# Impressum (§ 5 DDG / § 18 Abs. 2 MStV) — Pflichtangaben des Betreibers.
SITE_IMPRESSUM_NAME = "Haiko Springer"
SITE_IMPRESSUM_ADDRESS = ("Waldenburger Straße 46", "12621 Berlin, Deutschland")
SITE_IMPRESSUM_EMAIL = "haiko.springer@googlemail.com"
SITE_IMPRESSUM_NOTE = ("Renditeradar ist ein privates, redaktionelles Informations- und "
                       "Bildungsangebot rund um Finanzthemen. Die Inhalte stellen keine "
                       "Anlageberatung dar.")

# Wöchentliche Website-Hinweis-Story (src/bio_hint.py): fertige Vorlage in
# channels/<kanal>/assets/templates/, wird unverändert gepostet.
BIO_HINT_TEMPLATE = "story-bio-hinweis.jpg"

# ── Modul-Defaults (per .env überschreibbar: ENABLE_STOCKS/ENABLE_DIVIDEND) ─
# Finanz-only-Module: tägliche Aktien-Story-Cards (src/stocks/) + Dividenden-Posts.
ENABLE_STOCKS = True
ENABLE_DIVIDEND = True
# Website-Archiv + wöchentliche Hinweis-Story (ENABLE_SITE / ENABLE_BIO_HINT).
ENABLE_SITE = True
ENABLE_BIO_HINT = True
