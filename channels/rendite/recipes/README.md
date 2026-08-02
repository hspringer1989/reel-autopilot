# Reel-Rezepte (Renditeradar)

Referenz-Skripte für **Format B** — manuell gebaute Vergleichs-/Themen-Reels, die nicht
über `main.py stockreel` laufen (siehe „Zwei Bau-Wege" in der Haupt-`CLAUDE.md`).

Jedes Skript ist ein abgeschlossenes Beispiel: eigene PIL-Frames + eigenes Voiceover →
`src/render/renderer.py::render_reel(script, tts, broll_paths, out, music)` → Telegram-Freigabe.
Sie sind **nicht** Teil der Engine und laufen nicht automatisch — sie werden von Hand
gestartet und sind vor allem als Vorlage gedacht: Struktur abkupfern, Inhalte ersetzen.

Aufbau, der sich bewährt hat (5–6 Segmente):

```
Opener-Hook (heller, bunter Pexels-Clip)  →  4 gebrandete Vergleichs-Frames  →  CTA
```

| Skript | Muster |
|---|---|
| `build_chip_reel.py` | Länder-/Firmen-Vergleich mit Bewertungszahlen (die virale Vorlage) |
| `build_ruestung_reel.py`, `build_nuke_reel.py` | Branchen-Vergleich mit Ländergewichtung |
| `build_fed_reel.py`, `build_inflation_reel.py` | Makro-Ereignis + Marktreaktion |
| `build_hedgefonds_reel.py`, `build_meme_reel.py` | Erklärstück mit Gegenüberstellung |
| `build_servicenow_reel.py` | Einzelfirma ohne yfinance-Daten (eigene `MarketData`) |
| `build_week_reel.py`, `build_woche_reel.py`, `build_summer_reel.py` | Wochenausblick, frei betextet |
| `build_supermittwoch_reel.py` | Termin-Vorschau (mehrere Events an einem Tag) |
| `build_crash_anim.py` | animierte Frames statt Standbildern |

Die gelebten Regeln (Opener-Auswahl, Safe-Zone, Stimme, Zahlen als Wörter) stehen im
Skill `reel-redakteur` — vor dem Bauen dort nachlesen, danach LEARNINGS ergänzen.
