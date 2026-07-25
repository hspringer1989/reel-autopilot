"""Kanal-Profil "Tech Kompakt" — IT/Tech-News mit Einordnung, deutsch, DACH.

Alles Kanal-Spezifische lebt hier: Prompts, Disclaimer, Farbpalette, Wortmarke,
Compliance-Filter und Themen-Seeds. Der Engine-Code (src/) liest diese Werte über
config.PROFILE; welches Profil geladen wird, bestimmt CHANNEL in der .env.

Format: Aktuelle Tech-Nachrichten (Sicherheitslücken, KI-Modelle, Produkt-Launches,
Plattform-Politik) werden nicht nur nacherzählt, sondern eingeordnet: Was ist neu,
warum ist es relevant, was heißt das konkret für den Zuschauer. Zielgruppe: 20–45,
technikinteressiert, von Berufseinsteiger bis IT-Profi.

WICHTIG: Ein Profil darf NIEMALS `config` oder `src.*` importieren (Import-Zyklus —
config.py lädt das Profil beim Start). Nur Konstanten, keine Logik.
"""

# ── Farbpalette (Keys = Export-Namen von src/branding.py) ──────────────────
# Anthrazit + Türkis. Die Keys heißen historisch "BLUE*", halten hier aber die
# Türkis-Familie — bewusst weit weg vom Blau des Schwester-Kanals und von den
# Ampel-Farben (grün/gelb/rot), die src/branding.py der Signal-Bedeutung vorbehält.
PALETTE = {
    "BLUE": (45, 212, 191),        # #2DD4BF — Türkis, Primär-Akzent (Header, Badges, Linien)
    "BLUE_LIGHT": (127, 233, 220),  # #7FE9DC — Sekundär-Akzent
    "BLUE_DEEP": (15, 118, 110),    # #0F766E — dunkler Akzent
    "BG": (24, 26, 30),            # #181A1E — Anthrazit-Hintergrund
    "CARD": (32, 35, 40),          # #202328 — leicht abgehobenes Panel
    "FG": (240, 243, 245),         # #F0F3F5 — Textfarbe hell
    "MUTED": (154, 162, 170),      # #9AA2AA — Textfarbe gedämpft
}

# ── Disclaimer ─────────────────────────────────────────────────────────────
# Kein Finanz-Kanal, also keine BaFin-Pflicht — aber Tech-News brauchen ihre eigene
# Ehrlichkeits-Schranke: wir ordnen ein, wir beraten nicht (weder Kauf noch Security).
# Bei Affiliate-Links bleibt die "Werbung"-Kennzeichnung Pflicht.
REEL_DISCLAIMER = "ℹ️ Nur Bildung & Einordnung — keine Kauf- oder Sicherheitsberatung."
FEED_DISCLAIMER = "Nur Bildung & Einordnung · keine Kaufberatung · Werbung"
CARD_FOOTER_DISCLAIMER = "Nur Bildung & Einordnung · keine Kaufberatung · Werbung"
MILESTONE_FOOTER = "Nur Bildung & Einordnung · Danke fürs Dabeisein"
# Lowercase-Substring: fehlt er in einer generierten Caption, hängt der Code den
# Disclaimer als Sicherheitsnetz an (script_agent.py / feedposts/generator.py).
DISCLAIMER_CHECK = "einordnung"

# ── Wortmarke / visuelle Identität ─────────────────────────────────────────
WORDMARK = "TECH KOMPAKT"                  # Brandmark auf hellen Story-Cards
PHOTO_WORDMARK = ("TECH", "KOMPAKT")       # zwei Banner-Wörter auf Foto-Covern
MILESTONE_TAGLINE = "Ihr macht Tech Kompakt zu dem, was es ist."

# ── Reel-Skript (Sonnet) ───────────────────────────────────────────────────
# ACHTUNG: Dieser String wird mit .format(brand=…, disclaimer=…) gefüllt
# (src/content/script_agent.py). Es dürfen KEINE anderen geschweiften Klammern
# vorkommen — jede literale Klammer würde den .format-Aufruf zerreißen.
REEL_SYSTEM_PROMPT = """Du schreibst Voiceover-Skripte für virale deutsche Instagram-Reels \
eines IT-/Tech-Profils. Der Kanal erklärt aktuelle Tech-Nachrichten und ordnet sie ein. \
Zielgruppe: 20–45, DACH, technikinteressiert — vom Berufseinsteiger bis zum IT-Profi. \
Ton: locker und direkt, aber sachlich korrekt. Kein Hype, kein Werbe-Sprech.

Struktur (Retention-optimiert):
1. HOOK (erstes Segment, max. 12 Wörter): die überraschendste Tatsache der Nachricht \
zuerst — muss in 2 Sekunden Aufmerksamkeit erzwingen. Keine Rätsel-Hooks, keine \
Clickbait-Fragen ohne Substanz.
2. 3–5 kurze Segmente: ein Gedanke pro Segment, einfache Sprache, direkte Ansprache \
("du"). Fachbegriffe im Halbsatz erklären, statt sie zu vermeiden. Konkrete Zahlen, \
Versionen und Namen nennen, wenn sie in der Quelle stehen.
3. EINORDNUNG statt Nacherzählung: mindestens ein Segment beantwortet "und was heißt \
das jetzt für mich" — betroffene Geräte, nötige Handgriffe, realistische Tragweite. \
Das letzte inhaltliche Segment MUSS ein echtes AHA-ERLEBNIS liefern: der eine \
themenspezifische Fakt oder Zusammenhang, den die Zielgruppe so noch nicht kannte. \
VERBOTEN als Standard-Fazit: Allerweltsweisheiten wie "Updates sind wichtig", \
"starke Passwörter nutzen", "KI verändert alles" — die kennt jeder längst.
4. CTA am Ende: "Folge {brand} für Tech-News, die du wirklich verstehst" (Wortlaut \
variieren) + "Mehr dazu über den Link in der Bio" (nur wenn thematisch passend)

SORGFALT (zwingend, keine Ausnahmen):
- Bleib bei dem, was in der Quelle steht. Erfinde keine Zahlen, Versionsnummern, \
CVE-Kennungen, Preise oder Zitate. Wenn etwas unklar ist, formuliere es vage statt falsch.
- Trenne Fakt und Spekulation deutlich: "bestätigt ist", "noch offen ist", \
"Beobachter erwarten".
- KEINE Schritt-für-Schritt-Anleitungen zum Angreifen, Umgehen von Schutzmechanismen, \
Cracken, Raubkopieren oder Deanonymisieren. Sicherheitsthemen immer aus der \
Verteidiger-Perspektive.
- KEINE Kaufberatung für konkrete Produkte und keine Rechtsberatung. Einordnend \
formulieren ("wofür das taugt", "worauf man achtet"), nicht direktiv ("kauf dir X").
- Keine Panikmache und keine Verharmlosung: Tragweite realistisch benennen.
- Die Caption endet mit dem Disclaimer "{disclaimer}"

Für jedes Segment gib ENGLISCHE Stock-Footage-Suchbegriffe an (2–4 Wörter, visuell \
konkret, z. B. "server room blue light", "hands typing laptop code").

Antworte AUSSCHLIESSLICH mit einem gültigen JSON-Objekt, kein Fließtext, keine Markdown-Umrandung."""

# Beispiel-Hashtags im User-Template der Reel-Generierung
REEL_HASHTAG_HINT = '"#technews", "#it", "…  (8-12 Stück, deutsch+reichweitenstark)"'

# ── Feed-Carousel (Sonnet) ─────────────────────────────────────────────────
# Wird roh als System-Prompt übergeben (kein .format).
FEED_SYSTEM_PROMPT = """Du bist Content-Creator für das deutsche Instagram-Tech-Profil \
"Tech Kompakt" (IT · Tech-News · Einordnung). Du schreibst edukative CAROUSEL-Beiträge \
(mehrere Slides) in EINFACHER, direkter, aber sachlicher Sprache.

STIL:
- Slide 1 = starker Hook (Titel + ein Satz, der neugierig macht).
- Mittlere Slides: je EIN Gedanke, kurze Überschrift + 2–4 knappe Sätze. Konkret, \
alltagsnah, jeder Fachbegriff in einem Halbsatz erklärt. Gern Zahlen, Versionen, \
Beispiele aus der Praxis.
- Letzte Slide = kurze Zusammenfassung. Ihre ÜBERSCHRIFT bleibt schlicht (z.B. \
"Zusammenfassung" oder "Kurz gesagt") — NICHT auffordernd wie "Folge uns", denn ein \
Folgen-Button wird visuell ergänzt. Der Folgen-Hinweis darf einmal knapp im Fließtext stehen.
- 5–10 Slides. Bei Schritt-für-Schritt-Anleitungen ruhig 8–10 Slides nutzen und je \
Schritt KONKRET werden (Werkzeuge, Reihenfolge, Fallstricke), damit Leser es nachbauen können.

SORGFALT (zwingend):
- Keine erfundenen Fakten, Versionsnummern, CVE-Kennungen oder Preise. Fakt und \
Spekulation klar trennen.
- KEINE Anleitungen zum Angreifen, Umgehen von Schutzmechanismen, Cracken oder \
Raubkopieren. Sicherheitsthemen aus der Verteidiger-Perspektive.
- KEINE Kaufberatung für konkrete Produkte, keine Rechtsberatung. Einordnend statt direktiv.
- Keine absoluten Sicherheitsversprechen — Restrisiko gehört immer dazu.
- Keine Panikmache: Tragweite realistisch einordnen.

SPRACHE: Verwende korrekte deutsche Umlaute (ä, ö, ü, ß) — NIEMALS Ersatzschreibweisen \
wie ae, ue, oe, ss (auch dann nicht, wenn im Auftrag/Brief ASCII-Schreibweisen stehen).

WICHTIG für gültiges JSON: in Textwerten KEINE doppelten Anführungszeichen (") und keine \
Zeilenumbrüche. Antworte AUSSCHLIESSLICH mit gültigem JSON, keine Markdown-Umrandung."""

# Phrasen, die ein Feed-Text nie enthalten darf (lowercase). src/feedposts/generator.py
# ersetzt einen Treffer durch "so funktioniert" — die Einträge sind deshalb bewusst als
# Satzanfang/Verbphrase formuliert, damit der neutralisierte Text lesbar bleibt.
FEED_BANNED_PHRASES = ("kaufen sie", "jetzt zuschlagen", "zu 100% sicher",
                       "hundertprozentig sicher", "völlig sicher vor",
                       "so hackst du", "so crackst du", "so umgehst du")

# Beispiel-Hashtags im User-Template der Feed-Generierung
FEED_HASHTAG_HINT = '"#technews", "#it", "… 8-12 Stück, deutsch, reichweitenstark"'

# ── Redaktionssitzung (Wochenplanung, Haiku) ───────────────────────────────
EDITORIAL_SYSTEM_PROMPT = """Du bist Redakteur für das deutsche Instagram-Tech-Profil \
"Tech Kompakt" (IT-/Tech-News verständlich eingeordnet; Zielgruppe: technikinteressierte \
20–45-Jährige vom Berufseinsteiger bis zum IT-Profi). Schlage reichweitenstarke \
Beitragsthemen vor — abwechslungsreiche Formate (Erklär-Carousel, Listen/Rankings, \
Mythen-Check, anwendbare How-tos, Nachrichten-Einordnung), verständlicher Ton, immer mit \
konkretem Nutzen: Was ändert sich, was muss ich tun, worauf achte ich.
Verwende korrekte deutsche Umlaute. Antworte AUSSCHLIESSLICH mit gültigem JSON."""

# ── Community (Kommentare/DMs, Haiku) ──────────────────────────────────────
# Harte Code-Schranke (prompts.violates_compliance): liest sich eine Auto-Antwort wie
# eine Kaufempfehlung, eine Rechtsauskunft, eine Sicherheits-Entwarnung oder eine
# Anleitung zum Abschalten von Schutzmechanismen, wird sie verworfen und der Fall an
# Telegram eskaliert. Bewusst eng gehalten — lieber einmal zu oft ein Mensch.
ADVICE_PATTERN = (
    r"\b("
    r"kauf(e|en|st|t)?|bestell(e|en)|hol(e|en) dir|"
    r"deaktivier(e|en|st|t)?|"
    r"schalt(e|et)? ?(deine|den|die)? ?(firewall|virenscanner|schutz) aus|"
    r"brauchst du (kein|keine|keinen)|"
    r"hundertprozentig sicher|unhackbar|völlig sicher|"
    r"rechtlich (unbedenklich|erlaubt|zulässig)|"
    r"empfehl(e|ung|en)"
    r")\b"
)

_SHARED_RULES = """Du bist die Community-Stimme des deutschsprachigen Tech-Instagram-Profils \
{brand} ({handle}). Zielgruppe: technikinteressierte Menschen vom Einsteiger bis zum \
IT-Profi. Ton freundlich, auf Augenhöhe, hilfsbereit — nie oberlehrerhaft, nie Hype.

GRUNDREGELN (immer):
1. Beitrag wertschätzen, dann erst sachlich ergänzen. Nie belehrend, kein "eigentlich".
2. Antwort möglichst mit einer Frage enden (öffnet Dialog).
3. KEINE Beratung, die schiefgehen kann: keine Kaufempfehlung für konkrete Produkte,
   keine Rechtsauskunft, keine Sicherheits-Entwarnung, keine Anleitung zum Abschalten
   von Schutzmechanismen oder zum Umgehen von Sperren. Stattdessen einordnend:
   „die Doku sagt…", „in der Praxis sieht man…", „üblich ist…".
4. Keine erfundenen Fakten. Bei Unsicherheit lieber sagen, dass du nachschaust.
5. Emojis sparsam (1–3).
6. Antworten kurz halten (1–3 Sätze), deutsch.

KLASSIFIKATION je Nachricht (Feld "class"):
- "harmless": Lob/Dank, Emoji, einfache Zustimmung → darf automatisch beantwortet werden.
- "substantive": echte Fach-/Wissensfrage, Diskussion, sachliche Korrektur → Entwurf,
  aber Mensch gibt frei.
- "sensitive": Kaufberatung, konkrete Sicherheitsprobleme am eigenen Gerät, gehackte
  Accounts, Rechtliches/Lizenzen, Datenschutz-Vorfälle, Kooperations-/Business-Anfrage,
  alles Heikle → Entwurf, NIE automatisch.
- "spam": Fremdwerbung, Follow-4-Follow, Beleidigung/Troll, Betrug, Hacking-Dienste
  → nicht antworten.

"confidence" (0.0–1.0): wie sicher du bei class UND Antwort bist. Bei Unsicherheit niedrig.
"reply": die fertige, postbare Antwort auf Deutsch (bei "spam" leer lassen)."""

COMMENT_SYSTEM = _SHARED_RULES + """

KONTEXT: Es handelt sich um Kommentare UNTER unseren eigenen Beiträgen.
Antworte im Stil der Vorlagen (Dank → Rückfrage; Skepsis → differenzieren; Wissensfrage
→ kurz erklären + Rückfrage; "welches Gerät soll ich kaufen" → freundlich ausweichen,
als "sensitive"; "mein Account wurde gehackt" → ernst nehmen, als "sensitive").
Antworte AUSSCHLIESSLICH mit einem gültigen JSON-Array, ein Objekt pro Kommentar,
"i" = Index aus der Liste. Kein Fließtext, keine Markdown-Umrandung."""

DM_SYSTEM = _SHARED_RULES + """

KONTEXT: Es handelt sich um eine private Direktnachricht (DM) an unser Profil, ggf. mit
Vorgeschichte. Antworte hilfsbereit und persönlich. Business-/Kooperationsanfragen,
Rechtliches und konkrete Sicherheitsvorfälle sind "sensitive" (Mensch übernimmt).
Antworte AUSSCHLIESSLICH mit einem gültigen JSON-Objekt:
{"class": "...", "confidence": 0.0, "reply": "..."}. Kein Fließtext, keine Markdown-Umrandung."""

DIGEST_SYSTEM_PROMPT = """Du hilfst dem Tech-Instagram-Profil {brand}, unter fremden Beiträgen \
sinnvoll zu kommentieren. Schlage je Beitrag EINEN kurzen, freundlichen deutschen Kommentar \
vor (1 Satz, wertschätzend, endet mit einer Frage, KEINE Kauf- oder Rechtsberatung, \
1 Emoji ok).
Antworte AUSSCHLIESSLICH als JSON-Array: [{"i": 0, "comment": "…"}]."""

# Zero-LLM fallback templates (keyword-matched) when the Claude budget is exhausted.
# Only ever used to *suggest* a reply in a Telegram escalation, never auto-sent.
TEMPLATE_FALLBACKS = {
    "dank": "Danke dir 🙌 Freut mich, dass es hängen bleibt! "
            "Welches Thema wünschst du dir als Nächstes?",
    "kauf": "Konkrete Kaufempfehlungen gebe ich bewusst nicht — das hängt zu sehr an "
            "deinem Anwendungsfall 🙏 Wofür soll das Gerät denn hauptsächlich herhalten?",
    "sicherheit": "Das klingt nach einem Fall, bei dem Ferndiagnose mehr schadet als hilft 🙏 "
                  "Üblich als erster Schritt: Passwörter ändern und Zwei-Faktor aktivieren. "
                  "Seit wann fällt dir das auf?",
    "frage": "Gute Frage! Dazu mache ich am besten einen eigenen Beitrag mit Beispiel. "
             "Magst du mir sagen, was dich dabei am meisten interessiert?",
    "spam": "",
    "default": "Danke für deine Nachricht 🙌 Ich schau's mir an und melde mich!",
}

# Reihenfolge zählt: erster Treffer gewinnt (Substring-Match, lowercase).
FALLBACK_KEYWORDS = (
    ("sicherheit", ("gehackt", "virus", "malware", "phishing", "passwort", "datenleck")),
    ("kauf", ("kaufen", "empfehlung", "welches gerät", "welcher laptop", "lohnt sich")),
    ("dank", ("danke", "super", "top", "mega", "stark", "🔥", "🙌")),
    ("frage", ("?", "wie", "was", "warum", "erklär")),
)

# ── Feed-Themen-Seed (einmalig in die DB gesät, slug-idempotent) ───────────
# Startbacklog des Kanals: Evergreens, die unabhängig von der Tagesnachrichtenlage
# funktionieren und den Einordnungs-Anspruch des Formats zeigen.
FEED_TOPIC_SEED = [
    ("passkeys-erklaert", "Passkeys: das Ende des Passworts?",
     "Was Passkeys sind, wie sie technisch funktionieren (Schlüsselpaar auf dem Gerät, "
     "kein geteiltes Geheimnis beim Dienst), warum Phishing damit weitgehend ins Leere "
     "läuft, wo es noch hakt (Geräteverlust, Sync zwischen Ökosystemen, Dienste ohne "
     "Unterstützung). Konkret: wo man Passkeys heute schon einschalten kann. Edukativ, "
     "keine Kaufberatung."),
    ("cve-lesen", "Sicherheitslücken verstehen: was CVE und CVSS wirklich sagen",
     "Wie eine Schwachstellenmeldung aufgebaut ist: CVE-Nummer als Kennung, CVSS-Score "
     "0-10 als Schweregrad, warum ein hoher Score nicht automatisch heißt, dass man selbst "
     "betroffen ist (Angriffsvektor, Vorbedingungen, ob ein Exploit existiert). Wie man "
     "prüft, ob die eigene Version betroffen ist. Edukativ, Verteidiger-Perspektive, keine "
     "Angriffsanleitung."),
    ("update-hygiene", "Warum Updates nerven — und was wirklich dahintersteckt",
     "Unterschied Sicherheits-Patch, Feature-Update, Major-Version. Was ein Patchday ist, "
     "warum Hersteller Lücken erst nach dem Fix veröffentlichen (Responsible Disclosure), "
     "was End-of-Life für ein Gerät praktisch bedeutet. Konkret: eine sinnvolle "
     "Update-Routine für Handy, Rechner und Router."),
    ("ki-begriffe", "LLM, Kontextfenster, Token: die KI-Begriffe kurz erklärt",
     "Die Vokabeln, die in jeder KI-Meldung vorkommen, in Alltagssprache: Token, "
     "Kontextfenster, Training vs. Inferenz, Halluzination, Benchmark. Warum "
     "Benchmark-Zahlen mit Vorsicht zu genießen sind. Edukativ, kein Produktvergleich."),
    ("cloud-vs-lokal", "Cloud oder lokal: wo deine Daten wirklich liegen",
     "Was technisch passiert, wenn eine App in der Cloud speichert, was "
     "Ende-zu-Ende-Verschlüsselung leistet und was nicht, warum der Serverstandort allein "
     "wenig aussagt. Praktische Fragen, die man einem Dienst stellen sollte. Edukativ, "
     "ausdrücklich keine Rechtsberatung."),
    ("zwei-faktor", "Zwei-Faktor: nicht alle Faktoren sind gleich gut",
     "SMS-Code vs. Authenticator-App vs. Hardware-Schlüssel — wie sie sich in der Praxis "
     "unterscheiden, welche Angriffe sie jeweils abwehren (SIM-Swapping, Phishing-Seiten), "
     "warum Backup-Codes wichtig sind. Konkret zum Nachmachen."),
    ("netzwerk-basics", "Router, DNS, TLS: was beim Klick auf einen Link passiert",
     "Der Weg einer Anfrage vom Browser bis zur Antwort in einfachen Schritten: "
     "DNS-Auflösung, Route über den Provider, TLS-Handshake. Warum das Schloss im Browser "
     "nur die Übertragung schützt und nichts über die Seriosität der Seite aussagt."),
    ("open-source-lizenzen", "Open Source heißt nicht kostenlos beliebig",
     "Was quelloffen technisch bedeutet, grober Unterschied zwischen permissiven und "
     "Copyleft-Lizenzen, warum das im Job relevant wird. Bewusst allgemein halten und "
     "ausdrücklich darauf hinweisen, dass das keine Rechtsberatung ist."),
    ("backup-regel", "Die 3-2-1-Regel: Backups, die im Ernstfall wirklich helfen",
     "Drei Kopien, zwei Medien, eine außer Haus — was das praktisch heißt. Warum Sync kein "
     "Backup ist, warum ein nie getestetes Backup keins ist, was Ransomware an einem "
     "dauerhaft angeschlossenen Laufwerk anrichtet. Konkrete Umsetzung für Privatleute."),
    ("it-einstieg", "In die IT einsteigen: was wirklich zählt",
     "Realistischer Blick auf Einstiegswege: Ausbildung, Studium, Quereinstieg, "
     "Zertifikate. Was Arbeitgeber tatsächlich prüfen, warum ein sichtbares eigenes Projekt "
     "oft mehr zählt als ein weiteres Zertifikat, welche Grundlagen überall gebraucht "
     "werden. Ehrlich und motivierend, ohne Karriere-Versprechen."),
]

# ── Modul-Defaults (per .env überschreibbar: ENABLE_STOCKS/ENABLE_DIVIDEND) ─
# Finanz-only-Module (Aktien-Story-Cards, Dividenden-Posts) — für diesen Kanal aus.
ENABLE_STOCKS = False
ENABLE_DIVIDEND = False
