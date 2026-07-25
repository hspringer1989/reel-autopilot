# Onboarding: eigenen Kanal auf der Reel-Autopilot-Engine betreiben

Diese Anleitung richtet sich an einen neuen Mitentwickler, der die gemeinsame Engine
für einen **eigenen Instagram-Kanal** (eigenes Konto, eigener Server, eigene API-Keys)
betreiben will — z. B. einen IT/Tech-Kanal neben dem bestehenden Finanz-Kanal.

## Das Konzept in einem Absatz

Ein Prozess = ein Kanal. Alles Kanal-Spezifische (Prompts/Tonalität, Farbpalette,
Disclaimer, Wortmarke, Themen-Seeds, Bild-Templates) liegt in `channels/<name>/`;
die `.env` wählt mit `CHANNEL=<name>` das Profil und hält alle Instanz-Werte
(Tokens, Posting-Zeiten, Handles). Der Engine-Code in `src/`, `config.py` und
`main.py` ist kanal-neutral und wird gemeinsam entwickelt. **Dein Kanal-Ordner
gehört dir** — Änderungen dort brauchen kein Review. **Engine-Änderungen laufen
über Pull Requests** mit dem jeweils anderen als Reviewer, denn sie treffen beide
Produktiv-Instanzen beim nächsten `git pull`.

## 1. Projekt aufsetzen (lokal, offline)

```bash
git clone git@github.com:hspringer1989/reel-autopilot.git
cd reel-autopilot
python3.12 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

ffmpeg wird fürs Reel-Rendering gebraucht (`apt install ffmpeg` / `winget install ffmpeg`).

## 2. Eigenen Kanal anlegen

```bash
cp -r channels/_template channels/tech
touch channels/tech/__init__.py           # falls nicht mitkopiert
```

Dann `channels/tech/profile.py` ausfüllen — alle `TODO(<channel>)`-Stellen:
Prompts (Nische, Zielgruppe, Tonalität), Farbpalette, Disclaimer, Wortmarke,
Themen-Seed. Als Referenz für ein vollständiges Profil: `channels/rendite/profile.py`.

Eigene Bild-Templates nach `channels/tech/assets/templates/`:
- `feed_bg_title.png` + `feed_bg_content.png` (1080×1350) für Carousel-Slides
- ein Profilbild (Pfad per `BRAND_AVATAR` in der `.env` setzen)

## 3. .env anlegen (erst mal alles fake)

```bash
cp .env.example .env
```

Für den ersten Lauf ohne Kosten/Netz:

```ini
CHANNEL=tech
ENABLE_STOCKS=false        # Finanz-Module aus (Aktien-Story-Cards)
ENABLE_DIVIDEND=false      # dito (Dividenden-Posts)
LLM_PROVIDER=fake
TTS_PROVIDER=fake
STOCK_DATA_PROVIDER=fake
BRAND_NAME=DeinKanalname
BRAND_HANDLE=@dein.handle
REDDIT_SUBREDDITS=de_EDV,technik,…      # deine Nischen-Subreddits
RSS_FEEDS=https://…                     # deine Nischen-Feeds (Komma-getrennt)
```

## 4. Offline verifizieren

```bash
python -m pytest tests/        # muss grün sein (inkl. Profil-Vertragstest)
python main.py status          # DB/Queue-Überblick
python main.py collect         # Trends sammeln + scoren (fake-LLM)
python main.py generate        # ein Reel end-to-end (fake-TTS, Gradient-B-Roll)
python main.py feedpost        # ein Carousel aus deinem Themen-Seed
```

Die erzeugten Dateien liegen unter `data/reels/` bzw. `data/feed/` — Design prüfen
(Palette, Disclaimer, Wortmarke).

## 5. Echte Zugänge (jeder Kanal hat SEINE eigenen)

Reihenfolge wie in `docs/SETUP.md` (dort stehen die Detailschritte):
1. **Telegram-Bot** (@BotFather) + eigene Chat-ID → Review-Queue
2. **Instagram**: Creator-Konto, Meta-App, `IG_ACCESS_TOKEN`/`IG_USER_ID`
   (`python main.py verify-ig` prüft Token + Rechte)
3. **Anthropic-Key** (`LLM_PROVIDER=claude`, Budget via `CLAUDE_DAILY_BUDGET_EUR`)
4. **ElevenLabs** (`TTS_PROVIDER=elevenlabs`, deutsche Stimme wählen)
5. Optional **Pexels** (B-Roll) — ohne Key gibt es Gradient-Hintergründe

## 6. Server-Betrieb (beliebiger Linux-Host)

```bash
# auf dem Server
sudo apt install ffmpeg python3.12-venv
sudo git clone git@github.com:hspringer1989/reel-autopilot.git /opt/reel-autopilot
cd /opt/reel-autopilot && python3.12 -m venv venv && venv/bin/pip install -r requirements.txt
# .env anlegen (Werte aus Schritt 3+5), niemals committen!
```

systemd-Unit `/etc/systemd/system/reel-autopilot.service`:

```ini
[Unit]
Description=Reel Autopilot (Kanal: tech)
After=network-online.target

[Service]
WorkingDirectory=/opt/reel-autopilot
ExecStart=/opt/reel-autopilot/venv/bin/python main.py run
Restart=on-failure
RestartSec=30

[Install]
WantedBy=multi-user.target
```

Fürs echte Posten braucht Instagram eine öffentliche Medien-URL: nginx-Location auf
`PUBLIC_MEDIA_DIR` zeigen lassen und `PUBLIC_MEDIA_BASE_URL` setzen (siehe SETUP.md).

Deploy-Routine: `cd /opt/reel-autopilot && git pull && sudo systemctl restart reel-autopilot`.

## 7. Zusammenarbeit (Spielregeln)

- `main`/`master` ist immer deploybar; jede Instanz pullt, wann ihr Betreiber will.
- **Dein `channels/<name>/`**: direkt committen und pushen, kein Review nötig.
- **Engine (`src/`, `config.py`, `main.py`, `tests/`)**: kurzer Feature-Branch +
  PR, der andere reviewt. Vor dem Push: `python -m pytest tests/`.
- `.env`, `data/`, `venv/` sind gitignored — Secrets und die SQLite-DB bleiben
  auf der jeweiligen Instanz.
- Neue kanalabhängige Stellen im Engine-Code? Nicht hardcoden, sondern einen
  neuen Profil-Key einführen (+ in `channels/_template/profile.py` und
  `tests/test_profiles.py` ergänzen), damit beide Kanäle ihn setzen.
