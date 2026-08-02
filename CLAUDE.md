# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
pip install -r requirements.txt

python main.py collect            # collect + score trends only
python main.py generate           # produce one reel end-to-end → review queue
python main.py stocks             # build today's earnings + watchlist story cards → review
python main.py feedpost           # generate the next educational feed carousel → review
python main.py verify-ig          # read-only check of the IG token/account/permissions
python main.py run                # scheduler loop: review bot + story/feed slots + insights
python main.py publish --reel 3   # manually publish a specific reel
python main.py post-story --story 7  # manually publish a specific story card
python main.py post-feed --post 2 # manually publish a specific feed carousel
python main.py status             # queue counts, Claude budget, last posts

python -m pytest tests/           # offline: fake LLM/TTS, no network; ffmpeg test auto-skips
```

## Architecture

Autopilot that finds trending finance topics, produces German voiceover reels and
posts them to Instagram after human approval (Telegram review queue). Monetization
via a link-in-bio page with broker affiliate offers (Phase 4).

### Channel profiles (multi-channel)

One process = one channel. `CHANNEL` in `.env` selects `channels/<name>/profile.py`
(loaded once as `config.PROFILE`), which holds EVERYTHING channel-specific: system
prompts (reel/feed/editorial/community/digest/scorer), disclaimers + the caption
safety-net substring (`DISCLAIMER_CHECK`), the advice-pattern regex, fallback templates,
brand palette (re-exported by `src/branding.py`), wordmarks, milestone texts,
hashtag hints, the feed topic seed, the topic sources (`SOURCES`: rss feeds, subreddits,
google-trends on/off) with their scoring weights (`SCORER_WEIGHTS`), and module defaults.
Acquisition and scoring belong together: the broader a channel's sources, the heavier
`fit` must weigh, because more off-niche topics need discarding. `.env` still overrides
`RSS_FEEDS`/`REDDIT_SUBREDDITS`/`GOOGLE_TRENDS_ENABLED`/`SCORER_WEIGHTS` per instance.
Channel image templates
live in `channels/<name>/assets/templates/`. Finance-only modules are gated by
`ENABLE_STOCKS`/`ENABLE_DIVIDEND` (profile default, `.env` override); the morning
feed-build/milestone tick uses `DAILY_BUILD_SLOT` (defaults to `STOCK_STORY_SLOT`).
New channel: copy `channels/_template/` (see `docs/ONBOARDING.md`). Profiles must
never import `config` or `src.*`. When adding a channel-specific value to engine
code, add a profile key (+ `_template` + `tests/test_profiles.py`) instead of
hardcoding. Engine changes (`src/`, `config.py`, `main.py`) go through PRs; each
owner commits freely to their own `channels/<name>/`.

```
Collectors (google_trends | reddit | rss)      src/collectors/
        │  dedup via trends.uid
        ▼
Trend scorer — one batched Haiku call          src/content/scorer.py
  0.45·viral + 0.30·niche_fit + 0.25·monetization ≥ MIN_TREND_SCORE
        ▼
Script agent (Sonnet): hook-first German       src/content/script_agent.py
  script, caption, hashtags; compliance rules in the system prompt,
  "Keine Anlageberatung" disclaimer enforced in code
        ▼
TTS with word timestamps                       src/tts/  (elevenlabs | fake)
        ▼
Renderer (ffmpeg): per-segment Pexels b-roll   src/render/
  (or animated gradient fallback), karaoke ASS subtitles, music bed
  → 1080×1920 H.264
        ▼
Telegram review queue [✅ Posten|🔄 Neu|❌]      src/review/telegram_bot.py
        ▼
Publisher: Instagram Graph API                 src/publish/instagram.py
  stage MP4 under public URL → container → poll → publish → delete file
```

Reel status flow: `draft → pending_review → approved → published`
(reviewer can set `rejected` or `regenerate`; failures land in `failed` with `error`).

### Ports & fakes

Every paid/external dependency sits behind a port with an offline fake, so the whole
pipeline runs end-to-end without keys (`LLM_PROVIDER=fake`, `TTS_PROVIDER=fake`, no
Pexels key → gradient backgrounds, no Telegram → reels wait in DB):
`LLMProvider` (`src/content/llm.py`), `TTSProvider` (`src/tts/base.py`),
`PexelsBroll` (returns None → renderer falls back).

### Cost control (trading-bot pattern)

`src/content/usage.py`: hard daily gates — `CLAUDE_DAILY_BUDGET_EUR` (all Claude calls)
and `TTS_DAILY_BUDGET_CHARS` (ElevenLabs). No automatic call ever exceeds them.
Trend scoring uses `CLAUDE_MODEL_FAST` (Haiku, batched); only script generation uses
`CLAUDE_MODEL` (Sonnet).

### Database

SQLite at `data/reel_autopilot.db` (SQLAlchemy, `src/storage/database.py`):
`trends` (dedup + scores), `reels` (script/paths/status), `metrics` (daily insights),
`api_usage` (budget gating).

### Scheduler (`python main.py run`)

Minute tick: process 🔄 regenerations → keep review queue filled (generates when
queue < number of `POSTING_SLOTS`, 1h cooldown) → publish oldest approved reel at
each slot (local `TIMEZONE`) → fetch insights daily at 07:00. Rendering/LLM work
runs via `asyncio.to_thread` so the Telegram poller stays responsive.

### Daily stock stories (`python main.py stocks`)  — `src/stocks/`

A second content path, independent of the reel pipeline: **Instagram story cards**
(1080×1920 JPGs, not videos) for the daily stock routine.

```
EarningsCalendar.todays(universe)   src/stocks/market_data.py  (yfinance | fake)
        │  companies reporting quarterly figures today
        ▼
select_candidates(universe, N)      src/stocks/analyzer.py
  blended = STOCK_W_TECH·technical + STOCK_W_FUND·fundamental   (NO sentiment,
  like the trading-bot factor strategy) → top-N, DISTINCT sectors
        │  chart-derived risk marks: ATR stop/take (indicators.risk_levels)
        ▼
one budget-gated Claude call        analyzer._attach_analysis  (purpose="stock_analysis")
  educational text per candidate + overall take; rule-based fallback if over budget
        ▼
story cards (Pillow)                src/stocks/story_cards.py
  earnings card + watchlist-overview card + THREE cards per candidate
  (Charttechnik incl. drawn price chart / Fundamental / Gesamtbild), each with a
  traffic-light signal (green/amber/red = bullish/neutral/bearish, observational,
  NOT buy/sell). StoryRow.part = chart|fundamental|overall.
        ▼
StoryRow(pending_review)            src/storage/database.py  (table `stories`)
        ▼
Telegram photo review [✅ Posten | ❌]   send_photo_for_review / apply_story_decision
        ▼
publish_story (media_type=STORIES)  src/publish/instagram.py
  stage JPG under public URL → STORIES container → poll → media_publish → delete
```

- **Ports & fakes** like the rest: `STOCK_DATA_PROVIDER=fake` (`FakeMarketData` +
  `FakeEarningsCalendar`) runs the whole path offline; `indicators.py` is pure
  (SMA/RSI/ATR, technical/fundamental score, risk levels) and unit-tested with
  synthetic inputs. yfinance/Pillow are imported lazily inside methods.
- **Scheduler (`run`)** builds the cards once daily at `STOCK_STORY_SLOT` (→ Telegram
  review), then posts approved cards: earnings + watchlist-overview at
  `STORY_POST_EARNINGS_SLOT`, candidate cards spread over `STORY_SLOTS_EU` /
  `STORY_SLOTS_US` (local time; one story per slot, matched to the card's `market`).
  `publish_next_story` posts single cards (earnings/overview); `publish_next_candidate_group`
  posts a whole ticker's 3 cards in sequence. Approving one candidate card in Telegram
  cascades to all 3 of that ticker (the ✅/❌ sits on the overall frame; chart+fundamental
  are sent as context via `send_photo_plain`).
- Story cards bake ALL text into the image (Graph API stories have no
  stickers/links). No emoji in cards — the bundled fonts render them as tofu;
  emoji live only in Telegram captions. Story posting needs `PUBLIC_MEDIA_*`
  (public image URL) just like reels.

### Feed posts (educational carousels, 2×/week)  — `src/feedposts/`

A third content path (besides reels and stock stories): **permanent Instagram feed
carousels** (1080×1350 slides) on educational finance topics, posted Tue+Thu 17:00.

```
FeedTopicRow queue (seeded)         src/storage/database.py  (_FEED_TOPIC_SEED)
        │  next 'queued' topic (by position)
        ▼
build_feed_post (Sonnet)            src/feedposts/generator.py  (purpose="feed_post")
  5–8 slides {heading,body} + caption + hashtags; educational, no advice; JSON-robust
        ▼
render_feed_slides (Pillow)         src/feedposts/renderer.py
  slide 1 = hook + last = CTA on the blue radar template (assets/templates/feed_bg_title.png);
  middle = dark template (feed_bg_content.png). Text avoids the logo + bottom chart.
        ▼
FeedPostRow(pending_review)         table `feed_posts`
        ▼
Telegram review: slides as context + one caption msg with feed:approve/reject buttons
        ▼
publish_feed_post (CAROUSEL)        src/publish/instagram.py  (children + media_publish)
```

`main.py feedpost` builds one now; `main.py run` generates on a feed-slot day (morning) and
posts at the slot. `apply_feed_decision` handles the review buttons (`feed:` callback prefix).

### Weekly editorial loop (Redaktionssitzung) — `src/feedposts/editorial.py`

The week's posts are planned and approved entirely inside Telegram — **nothing is generated
before the plan is approved, and nothing is posted before each single post is approved.**

```
FEED_EDITORIAL_DAY/TIME (Sun 11:00)   send_editorial_reminder
  propose_week_topics (Haiku)  →  WeekPlanRow(pending_review)  →  Telegram message
     [✅ Beiträge erstellen] [🔄 Neue Themen] [❌ Verwerfen]      (`plan:` callbacks)
        │                          ↩️ reply with a wish → revise_week_topics (Haiku)
        │                             → plan updated → re-sent for approval
        ▼  ✅
  build_approved_plan  (detached task; generation takes minutes)
     generate_week_posts → one FeedPostRow per topic, scheduled_at = its day 17:00
        ▼
  every post individually:  slides + caption + [✅ Posten] [✏️ Ändern] [❌ Verwerfen]
        │                   ↩️ reply with a wish → regenerate_feed_post (in place,
        │                      keeps id + slot) → back to review
        ▼  ✅
  publish_due_scheduled_feed_posts posts it at its scheduled_at (+ announcement story)
```

- The proposal is **persisted** (`week_plans`) — the topic list is never lost, and the plan
  is reachable later by its Telegram message id (`plan_by_tg_message`) for the reply flow.
- `plan_slots` never returns a past slot: approving a plan late shifts the days forward
  instead of publishing instantly.
- Both reply flows are routed in `_on_reply` (plan → feed post → community escalation).
- `main.py weekplan` sends the Redaktionssitzung on demand; the ✅ button is processed by
  the polling loop of `main.py run`.

### Brand palette — `src/branding.py`

Shared blue-on-dark Renditeradar palette (BLUE #2386D1, matching the Claude-Design templates)
+ Pillow helpers (`load_font`, `wrap`, `market_badge`), used by BOTH `story_cards.py` and the
feed renderer so stories and feed posts look consistent. Traffic-light green/amber/red stays
reserved for the signal meaning, not the brand accent.

### Ticker cooldown

`build_daily_stories` excludes tickers analysed in the last `STOCK_REPEAT_COOLDOWN_DAYS` (30)
via `_recent_candidate_tickers`; `select_candidates(exclude=…)` holds them back and only reuses
them as a last resort. `STOCK_UNIVERSE` was widened to ~90 US+EU names to feed the cooldown.

### Community automation (DMs, comments, engagement digest) — `src/community/`

A fourth path, independent of content generation: auto-replies to comments on our own
posts and to DMs, plus a daily engagement digest. Polled inside the scheduler tick
(no webhook server); every external call sits behind `CommunityAPI` (`api.py`) with a
`FakeCommunityAPI`; all Claude calls use Haiku through the budget-gated `LLMProvider`.

```
scheduler tick (every COMMUNITY_POLL_MINUTES)
  poll_comments()  src/community/comments.py   fetch own recent media's comments →
      dedup (comments table) → classify_comments (Haiku, batched) → route:
        harmless+conf≥MIN → auto-reply | substantive/sensitive/low-conf → Telegram
        approval | spam → skip.  Shadow mode classifies + notifies, never posts.
  poll_dms()       src/community/dms.py         /me/conversations → dedup (dm_messages)
      → classify_dm → auto-reply within the 24h window / escalate sensitive+closed.
  build_digest()   src/community/digest.py      hashtag search (usually unavailable on
      Instagram-Login) → fallback to profiles + collector topics → Telegram list.
```

- **Routing/compliance**: classifier (`classifier.py`) + prompts from
  `docs/community-antworten.md` (`prompts.py`); a code-level phrase filter
  (`violates_compliance`) forces any advice-sounding auto-reply to `sensitive`
  (human review). `sensitive` is NEVER auto-answered.
- **Telegram**: `cmt:`/`dm:` callback prefixes + a reply-to-message edit flow in
  `src/review/telegram_bot.py`; `resolve_review`/`resolve_edit` live in the pipelines.
- **Guards** (`guard.py`): `COMMUNITY_ENABLED` kill-switch, `COMMUNITY_SHADOW_MODE`,
  combined hourly rate limit, own-account filter, 24h DM window.
- **Gates** roll out in phases: comments shadow → comments live → `COMMUNITY_DM_ENABLED`
  → `COMMUNITY_DIGEST_ENABLED`. Manual cycle: `python main.py community`; capability
  check: `python main.py verify-ig` (probes the comment/DM/hashtag edges).
- **Out of scope by design**: no auto commenting/liking/following on foreign profiles
  (no official API, ToS violation) — the digest replaces it with manual suggestions.

## Compliance (do not weaken)

- Scripts must stay educational/news-driven — no buy/sell recommendations for
  specific securities (BaFin finfluencer rules). The disclaimer append in
  `script_agent.py` is a safety net, not decoration.
- Affiliate content must be labelled as Werbung (caption + landing page).
- Only royalty-free music from `assets/music/` — API-published reels have no license
  for Instagram's in-app music library.

## Setup

Manual steps (Instagram/Meta app, ElevenLabs, Telegram, affiliate networks):
see `docs/SETUP.md`. Local dev `.env` uses fakes; production values per `.env.example`.

---

# Reel-Redaktion — Praxiswissen (Renditeradar)

Hart erarbeitetes Handwerkswissen für die manuelle Reel-Erstellung (ergänzt die Architektur oben).
Die **lebende** Fassung liegt im Skill `reel-redakteur` (`~/.claude/skills/reel-redakteur/`:
SKILL.md · playbook.md · build-recipes.md · LEARNINGS.md) — dort vor jedem Reel lesen, danach
LEARNINGS ergänzen; bei Reichweiten-/Share-Daten die Playbook-Defaults verdichten.
Grundregel: **kein öffentlicher Post ohne Telegram-✅**; rein edukativ, Disclaimer, keine Beratung.

## ⭐ Gewinner-Formel (belegt: Chip-Reel ging viral)
1. **Inhaltliche Tiefe + smarter, erklärender VERGLEICH** → wird GETEILT → Reichweite. Substanz nie
   für Kürze opfern. Vergleichsformat (mehrere Firmen/Länder/Optionen, echte Zahlen) = Gewinner.
2. **Heller, farbenfroher HERO-Opener** = Grid-Vorschaubild = erster Stopp.
3. **Fluente Stimme + sauberer Text.**  4. **Aktuelles Ereignis** + **frisches, themenspezifisches Aha**.

## Zwei Bau-Wege
- **Format A — Einzelaktie:** `src/stocks/stock_reel.py::build_stock_reel(ticker, topic, md, llm,
  texts, caption, hook_query, cta_query)`. yfinance-Realdaten; ohne Daten (frischer IPO) eigene
  `MarketData`-Subklasse mit recherchierten Werten. `texts` = eigenes Voiceover.
- **Format B — Vergleich/Thema (manuell, für virale Reels):** eigene PIL-Frames + `src/render/
  renderer.py::render_reel(script, tts, broll_paths, out, music)`. `broll_paths` = 1/Segment
  (Bild=Standbild, Video=Clip, None=Verlauf); Untertitel global aus `tts.words`. Frames mit
  `src/branding.py`. **Muster-Skripte auf dem Server:** `build_chip_reel.py`, `build_ruestung_reel.py`,
  `build_fed_reel.py`, `build_nuke_reel.py` (Struktur: Opener-Hook → 4 Frames → CTA, 5–6 Segmente).
- **`title` im script_json PFLICHT** → `announce_new_reel` nimmt ihn für die „NEUES REEL"-Story;
  fehlt er → nur „Neues Reel" (Follower wissen nicht, worum es geht).

## Opener (höchste Priorität)
- **Hell + farbenfroh + klarer HERO** (Objekt/Person/Gebäude/Tier scharf im Bild). NICHT dunkel,
  NICHT weit/abstrakt. **Pexels-Clip per fester ID forcieren** (fetch monkeypatchen), Poster
  (`v['image']`) VOR Nutzung sichten. Suche unzuverlässig (rocket→Spielzeug, tank→Wasserturm,
  chip/tech→dunkel). Fehlt ein Motiv: ehrlich sagen + Alternativen zur Wahl geben.
- Bewährte IDs: Erde-All 20349219 · Ara-Papagei 12715038 · Kühlturm+Himmel 37544749 ·
  NYSE+Flagge 5635831 · warme Farbwellen 34336248 · buntes Paint 9668305 (CTA).

## Frame-Safe-Zone
Inhalt nur y≈290–1250 (`TOP=290`). Oben ~15 % frei (IG-Profilname), unten Untertitel (ASS
`MarginV=500`). **Am echten Video-Frame verifizieren** (`ffmpeg -ss t -i reel.mp4 -frames:v 1`).
Engine-Frames in `stock_reel.py` sitzen noch zu hoch (offener PR-Fix).

## Stimme / Text (STRIKT)
- Stimme = **Thomas** `5faieqDE3osz75KiOI2M` (DE), Settings **0.40 / 0.40 / 1.06** — nicht ohne
  Anlass wechseln (Konsistenz). Fluss kommt v. a. über sauberen Text.
- **Zahlen IMMER als Wörter** im Voiceover („hundertfünfundzwanzig", „sechsundachtzig Dollar") —
  bloße Ziffern nuschelt die Engine. Frames zeigen Ziffern.
- **Knifflige Wörter phonetisch:** „Uran" → „Uraan"; lange Komposita auflösen. Frames behalten die
  korrekte Schreibweise. Audio kann ich nicht hören → User gegenchecken lassen.

## Inhalt
- Aufhänger = **aktuelles Ereignis**, per WebSearch verifizieren (Datum + Zahlen).
- **⏱️ DATUM NENNEN (PFLICHT):** nie nur „heute"/„gestern" — immer das konkrete Datum (Voiceover
  UND Frames), z. B. „am 29. Juli 2026", „Stand Ende Juli 2026". Reels bleiben dauerhaft online.
- Verifikation vor dem Senden: je Frame ein echtes Video-Frame prüfen (Opener hell/bunt/Hero?
  Safe-Zone? Untertitel frei? Zahlen korrekt?).

## Veröffentlichung
- **Reel 09:00:** `publish_next_approved()` postet das ÄLTESTE freigegebene Reel + Ankündigung.
  → vor 09:00 freigeben; sicherstellen, dass KEIN anderes Reel 'approved' ist; Ersatz-Reels auf
  `rejected`.
- **Custom-Zeit (12:00/15:00/15:30):** kein Auto-Slot → **detached Watcher** (`setsid nohup … &`),
  der bei (`approved` UND Zielzeit) postet (`publish_reel`+`announce_new_reel` bzw. `_publish_one`
  für Stories). Doppelvarianten: Watcher wählt die freigegebene, verwirft die andere.
- **Tages-Stories:** date-locked auf heute; **Nachhol-Logik** postet nach 09:30 freigegebene
  Earnings/Watchlist binnen ~60 s. **Feed-Carousels:** `FEED_POST_SLOTS` täglich 17:00 ODER
  `scheduled_at` pro Post; Ankündigung eingebaut („freigegeben ≠ eingeplant"). **Meilenstein-Story**
  bei 500/1000/… (auto, postet nach ✅). **Follower-Wunsch:** `build_candidate_for_ticker(…,
  category="FOLLOWER-WUNSCH · @handle")`.

## Deploy & Gotchas
- **gzip-Transfer** (cat truncatet bei Reset); `-o ServerAliveInterval=10`.
- **Nach `generator.py`/`main.py`-Änderung Service-Restart** — aber vormittags nur mit
  Doppel-Batch-Schutz. Der Dienst überschreibt CLI-`buildsite` mit altem In-Memory-Generator →
  gegen die LIVE-Seite verifizieren.
- **Doppel-Batch-Guard** (main.py): Build überspringen nur, wenn `kind IN ('candidates','earnings')`
  für heute existiert (NICHT manuelle `'candidate'` — eine früh erstellte Einzel-Analyse wie GRAB
  hat sonst den Tages-Build blockiert).
- **Instant-Publish:** Reel-„Posten" setzt nur `approved` (postet am Slot); Feed-Posts posten sofort.
- **Multichannel:** Engine mit dem Kanal des Bruders geteilt → **Engine-Änderungen nur per PR**,
  nichts kanalabhängiges hardcoden. Direkte Server-Edits sind Notlösung, danach committen/PR'en.

## Verwandte Tools
- Skill `reel-redakteur` (selbstlernend). Morgen-Briefing (systemd-Timer `reel-briefing` 08:00 →
  Telegram-Tagesplan + Freigabe-Lücken + News-Reel-Ideen, `morning_briefing.py`). Website
  renditeradar.eu (Generator, Cutoff 24.07., Jahr/Monat/Tag-Filter, wöchentl. Website-Hinweis-Story
  Fr 20:00 ohne Freigabe). Skill `insta-kommentar` + Kommentar-Studio (eigener Rendite-Radar-Key).
