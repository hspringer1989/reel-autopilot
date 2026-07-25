"""System prompts + compliance guardrails for community auto-replies.

The rules and tone are lifted from docs/community-antworten.md (the manual
reply guide) so automated replies sound exactly like the hand-written ones and
stay within BaFin finfluencer limits: educational/observational, never advice.
"""
import re

# Words that make a reply read like investment advice — a hard code-level safety
# net (mirrors the disclaimer append in script_agent.py). Any auto-reply matching
# these is discarded and the item is escalated to Telegram instead.
_ADVICE_PATTERNS = re.compile(
    r"\b("
    r"kauf(e|en|st|t)?|verkauf(e|en|st|t)?|"
    r"einsteig(en|st|t)|zuschlag(en|t)|"
    r"kursziel|preisziel|"
    r"solltest du|würde ich (kaufen|nehmen|einsteigen|verkaufen)|"
    r"empfehl(e|ung|en)|garantiert(e|er)? (gewinn|rendite)"
    r")\b",
    re.IGNORECASE,
)


def violates_compliance(text: str) -> bool:
    """True if a drafted reply reads like a buy/sell/target recommendation."""
    return bool(_ADVICE_PATTERNS.search(text or ""))


# Shared grounding for both comment and DM classification/drafting.
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


def suggest_template(text: str) -> str:
    """Pick a keyword-matched fallback suggestion (budget-exhausted path)."""
    low = (text or "").lower()
    if any(w in low for w in ("kauf", "verkauf", "kursziel", "einsteig")):
        return TEMPLATE_FALLBACKS["kauf"]
    if any(w in low for w in ("danke", "super", "top", "mega", "stark", "🔥", "🙌")):
        return TEMPLATE_FALLBACKS["dank"]
    if "?" in low or any(w in low for w in ("wie", "was", "warum", "erklär")):
        return TEMPLATE_FALLBACKS["frage"]
    return TEMPLATE_FALLBACKS["default"]
