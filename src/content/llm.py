"""LLM provider port. Claude for production, FakeLLM for offline tests
(same idea as the LLMProvider port in Lead_Generator)."""
import json
import re
from abc import ABC, abstractmethod

from loguru import logger

import config
from src.content import usage


class LLMProvider(ABC):
    @abstractmethod
    def complete(self, system: str, user: str, model: str, max_tokens: int, purpose: str) -> str:
        """Return the raw text completion. Raises BudgetExceeded if the daily cap is hit."""

    def research(self, system: str, user: str, model: str, max_tokens: int,
                 purpose: str, max_searches: int = 6) -> str:
        """Answer using Anthropic's server-side web search — the only way this host can
        reach the live web (no outbound scraping, no search API key of our own).

        Default implementation falls back to `complete()`, so a provider without web
        access (FakeLLM in tests) still returns something usable instead of raising.
        """
        return self.complete(system, user, model, max_tokens, purpose)

    def judge_image(self, system: str, user: str, image_jpeg: bytes, model: str,
                    max_tokens: int, purpose: str) -> str:
        """Judge an image and return text. Used to pick reel openers by eye instead of
        by brightness arithmetic — a bright frame can still be the wrong picture.

        Default implementation ignores the image and falls back to `complete()`.
        """
        return self.complete(system, user, model, max_tokens, purpose)


class BudgetExceeded(RuntimeError):
    pass


class ClaudeProvider(LLMProvider):
    def __init__(self):
        import anthropic

        # timeout/max_retries: a hung call must never block a pipeline run
        self._client = anthropic.Anthropic(
            api_key=config.ANTHROPIC_API_KEY, timeout=120.0, max_retries=2
        )

    def complete(self, system: str, user: str, model: str, max_tokens: int, purpose: str) -> str:
        if usage.claude_budget_exceeded():
            raise BudgetExceeded("Claude-Tagesbudget erschöpft")
        message = self._client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
        )
        usage.record_claude(
            model, message.usage.input_tokens, message.usage.output_tokens, purpose
        )
        return message.content[0].text


    # Der Client-Timeout (120 s) ist fuer normale Textcalls gedacht und fuer einen
    # Recherche-Call zu knapp: der fuehrt die Websuchen serverseitig aus, bevor das
    # erste Token kommt.
    #
    # Aber grosszuegig darf er auch nicht sein. Mit 600 s hing die Abend-Automatik am
    # 20.08.2026 ueber 40 Minuten in einem gedrosselten Aufruf. Ein Reel, das um 19:05
    # fertig ist, ist mehr wert als eines, das um 19:45 vielleicht kommt — reisst die
    # Recherche dieses Budget, faellt die Automatik lieber sofort auf den RSS-Pfad.
    RESEARCH_TIMEOUT_S = 180.0

    def research(self, system: str, user: str, model: str, max_tokens: int,
                 purpose: str, max_searches: int = 6) -> str:
        """Server-side web search. Anthropic runs the queries; we get text + citations.
        Costs more input tokens than a plain call (search results enter the context),
        so the daily budget gate matters here more than anywhere else.

        Gestreamt, nicht als ein Block angefordert: bei einem Aufruf, der erst sucht und
        dann eine lange Antwort schreibt, laeuft sonst der Lesevorgang in den Timeout,
        obwohl der Server noch arbeitet."""
        if usage.claude_budget_exceeded():
            raise BudgetExceeded("Claude-Tagesbudget erschöpft")
        # max_retries=0: der Client wiederholt sonst zweimal, aus 180 s werden
        # dann 9 Minuten. Genau das hat die Automatik am 20.08.2026 haengen
        # lassen. Ein Fehlschlag soll hier SCHNELL passieren, damit der
        # RSS-Pfad noch rechtzeitig uebernehmen kann.
        client = self._client.with_options(
            timeout=self.RESEARCH_TIMEOUT_S, max_retries=0)
        with client.messages.stream(
            model=model,
            max_tokens=max_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
            tools=[{"type": "web_search_20260209", "name": "web_search",
                    "max_uses": max_searches}],
        ) as stream:
            message = stream.get_final_message()
        usage.record_claude(
            model, message.usage.input_tokens, message.usage.output_tokens, purpose
        )
        # A search turn returns interleaved blocks (server_tool_use, results, text).
        # Only the text blocks carry the answer; join them in order.
        return "\n".join(b.text for b in message.content if b.type == "text")

    def judge_image(self, system: str, user: str, image_jpeg: bytes, model: str,
                    max_tokens: int, purpose: str) -> str:
        import base64

        if usage.claude_budget_exceeded():
            raise BudgetExceeded("Claude-Tagesbudget erschöpft")
        message = self._client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {
                    "type": "base64", "media_type": "image/jpeg",
                    "data": base64.standard_b64encode(image_jpeg).decode(),
                }},
                {"type": "text", "text": user},
            ]}],
        )
        usage.record_claude(
            model, message.usage.input_tokens, message.usage.output_tokens, purpose
        )
        return "\n".join(b.text for b in message.content if b.type == "text")


class FakeLLM(LLMProvider):
    """Deterministic canned responses for tests: maps a purpose to a response."""

    def __init__(self, responses: dict[str, str]):
        self.responses = responses
        self.calls: list[dict] = []

    def complete(self, system: str, user: str, model: str, max_tokens: int, purpose: str) -> str:
        self.calls.append({"system": system, "user": user, "model": model, "purpose": purpose})
        return self.responses[purpose]


def _balanced_span(text: str) -> str | None:
    """First balanced {...} or [...] span, ignoring braces inside strings.

    Needed because a web-search turn often narrates its findings before answering,
    so the JSON is neither at the start nor the end of the response.
    """
    start = min((i for i in (text.find("{"), text.find("[")) if i != -1), default=-1)
    if start == -1:
        return None
    opener = text[start]
    closer = "}" if opener == "{" else "]"
    depth, in_string, escaped = 0, False, False
    for i, ch in enumerate(text[start:], start):
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def parse_json_response(raw: str):
    """Parse a JSON object/array from an LLM response, tolerating ``` fences and
    surrounding prose."""
    # strict=False tolerates literal control chars (e.g. newlines) inside strings.
    candidates = []
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    cleaned = re.sub(r"\s*```$", "", cleaned)
    candidates.append(cleaned)

    fenced = re.search(r"```(?:json)?\s*(.+?)\s*```", raw, re.DOTALL)
    if fenced:
        candidates.append(fenced.group(1))

    span = _balanced_span(raw)
    if span:
        candidates.append(span)

    for candidate in candidates:
        try:
            return json.loads(candidate, strict=False)
        except json.JSONDecodeError:
            continue
    logger.warning(f"LLM-Antwort kein gültiges JSON — {cleaned[:160]}")
    return None


def builtin_fake() -> "FakeLLM":
    """Offline stand-in (LLM_PROVIDER=fake): lets the whole pipeline run end-to-end
    without API keys or costs — used for local dry-runs and tests."""
    scores = json.dumps([
        {"i": i, "viral": 0.8 - i * 0.05, "fit": 0.9, "monetization": 0.7,
         "reasoning": "Fake-Bewertung für Offline-Test"}
        for i in range(25)
    ])
    script = json.dumps({
        "title": "Offline-Testskript",
        "segments": [
            {"text": "Diese drei Geldfehler kosten dich zehntausende Euro.", "broll": "burning money close up"},
            {"text": "Fehler eins: Dein Geld liegt unverzinst auf dem Girokonto und verliert jedes Jahr an Wert.", "broll": "empty wallet person"},
            {"text": "Fehler zwei: Du wartest auf den perfekten Einstieg, statt einfach anzufangen.", "broll": "stock market chart"},
            {"text": "Fehler drei: Du zahlst hohe Gebühren für Produkte, die du nicht verstehst.", "broll": "signing contract documents"},
            {"text": "Folge für mehr Finanzwissen — den Rest findest du über den Link in der Bio.", "broll": "smartphone social media"},
        ],
        "caption": "Drei Fehler, die dich still und leise Geld kosten 💸\n\n⚠️ Keine Anlageberatung — nur Bildung & Unterhaltung.",
        "hashtags": ["#finanzen", "#geld", "#sparen", "#investieren", "#finanzwissen"],
    })
    stock_analysis = json.dumps({
        "candidates": [
            {
                "ticker": t,
                "chart": ("Der Kurs notiert über 20- und 50-Tage-Linie, die Struktur bleibt aufwärts. "
                          "Der RSI um 55 (Schwungkraft-Maß) zeigt Luft nach oben ohne Überhitzung, keine Empfehlung."),
                "fundamental": ("Mit KGV rund 18 ist die Aktie moderat bewertet (KGV = Preis je Euro Gewinn). "
                                "Das Umsatzplus von 10% und eine Marge von 20% stützen das Geschäft. "
                                "Datenbasierte Einordnung, keine Empfehlung."),
                "overall": ("Chart und Fundamentaldaten stützen sich gegenseitig – ein stimmiges Bild. "
                            "Chance ist die Zielmarke, Risiko der Rückfall unter die Stop-Marke. Keine Empfehlung."),
            }
            for t in ("AAPL", "JPM", "XOM", "SAP.DE", "ALV.DE")
        ],
    })
    feed_post = json.dumps({
        "title": "So wählen wir Aktien für unsere Analysen aus",
        "slides": [
            {"heading": "Wie funktioniert die Auswahl?",
             "body": "Wir kombinieren zwei Blickwinkel: Charttechnik und Fundamentaldaten. "
                     "Jeder Titel bekommt einen Score — ganz ohne Bauchgefühl."},
            {"heading": "Charttechnik",
             "body": "Wir schauen auf den Trend (Kurs über 20- und 50-Tage-Linie) und den RSI, "
                     "ein Maß für die Schwungkraft. Gesund ist ein RSI zwischen 45 und 65."},
            {"heading": "Fundamental",
             "body": "Wir prüfen KGV (wie teuer je Euro Gewinn), Umsatzwachstum und Gewinnmarge. "
                     "Günstig bewertet plus Wachstum ist ein starkes Zeichen."},
            {"heading": "Der Gesamt-Score",
             "body": "50% Charttechnik + 50% Fundamental ergeben eine Ampel: grün, gelb oder rot. "
                     "Wir wählen Titel aus VERSCHIEDENEN Branchen für Streuung."},
            {"heading": "Zusammenfassung",
             "body": f"Jeden Tag frische, datenbasierte Einordnungen — folge {config.BRAND_HANDLE} "
                     "für mehr. Keine Anlageberatung."},
        ],
        "caption": "So läuft unsere Aktien-Auswahl ab — transparent und datenbasiert.\n\n"
                   "Keine Anlageberatung · nur Bildung.",
        "hashtags": ["#finanzen", "#aktien", "#börse", "#investieren", "#charttechnik"],
    })
    trend_ticker = json.dumps(
        {"ticker": "XOM", "name": "Exxon Mobil", "reason": "steht wegen Quartalszahlen im Fokus"}
    )
    week_plan = json.dumps({"topics": [
        {"slug": f"thema-{i}", "title": f"Beispiel-Thema {i}", "brief": "Kurzer Brief mit Entscheidungslogik."}
        for i in range(1, 8)
    ]})
    # Community: classify a batch of comments (harmless auto-reply by default).
    community_comments = json.dumps([
        {"i": i, "class": "harmless", "confidence": 0.9,
         "reply": "Danke dir 🙌 Welches Thema wünschst du dir als Nächstes?"}
        for i in range(20)
    ])
    community_dm = json.dumps(
        {"class": "harmless", "confidence": 0.9,
         "reply": "Danke für deine Nachricht 🙌 Wie kann ich dir weiterhelfen?"}
    )
    community_digest = json.dumps([
        {"i": i, "comment": "Spannender Beitrag 🙌 Wie siehst du das mittelfristig?"}
        for i in range(10)
    ])
    # Offline gilt jedes Segment als gedeckt — sonst wuerde jeder Trockenlauf
    # Warnungen zeigen, die nichts mit dem Skript zu tun haben.
    fact_check = json.dumps([])
    return FakeLLM({
        "score_trends": scores, "generate_script": script,
        "stock_analysis": stock_analysis, "feed_post": feed_post,
        "trend_ticker": trend_ticker, "week_plan": week_plan,
        "community_comments": community_comments, "community_dm": community_dm,
        "community_digest": community_digest, "fact_check": fact_check,
    })


def get_llm() -> LLMProvider:
    if config.LLM_PROVIDER == "fake":
        return builtin_fake()
    return ClaudeProvider()
