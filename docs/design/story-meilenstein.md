# Handoff: Instagram-Story „Follower-Meilenstein" (Rendite Radar)

## Overview
Eine Instagram-Story-Grafik (1080×1920), die einen erreichten Follower-Meilenstein feiert
(z. B. 1.000 Follower), sich bei den Followern bedankt und zum Teilen des Kanals auffordert,
um das nächste Ziel (z. B. 2.000) zu erreichen. Die Karte soll bei jedem neuen Meilenstein
erneut gepostet werden — es müssen dann nur drei Zahlen gesetzt werden.

Kanal: @rendite.radar.official (Aktienanalysen und Finanzthemen, deutschsprachig).

## About the Design Files
Die Datei in diesem Bundle ist eine **Design-Referenz in HTML** — ein Prototyp, der
Aussehen und Aufbau zeigt, **kein Produktionscode zum direkten Übernehmen**.
Aufgabe ist es, dieses Design in der Zielumgebung nachzubauen (React, Vue, Svelte,
SwiftUI, native, oder ein Node-Script mit Headless-Browser) und dabei die dort
etablierten Muster und Libraries zu verwenden. Existiert noch keine Umgebung, das für
den Zweck am besten geeignete Framework wählen.

Konkreter Zweck hier: Das Ergebnis muss ein **PNG mit exakt 1080×1920 px** sein, das als
Instagram-Story hochgeladen werden kann. Ein pragmatischer Weg ist, das HTML unverändert
zu rendern (Puppeteer/Playwright) und das Story-Element als PNG zu exportieren — siehe
"Export" weiter unten.

## Fidelity
**High-fidelity.** Alle Farben, Schriftgrößen, Abstände, Radien und Texte sind final und
unten exakt dokumentiert. Der Nachbau soll pixelgenau erfolgen.

## Screens / Views

### Screen: Meilenstein-Story
- **Name:** Follower-Meilenstein-Story
- **Purpose:** Meilenstein feiern, danken, zum Teilen animieren.
- **Canvas:** exakt 1080×1920 px, `overflow: hidden`, Hintergrund `#0c1512`,
  Root ist ein `flex column`. Kein Eckenradius (Instagram zeigt die Story vollflächig).
- **Wichtig — Instagram-Safe-Zone:** Die obersten **170 px** bleiben inhaltsfrei
  (leerer Spacer). Instagram legt dort den Profilnamen über die Story.
  Unten sollten die letzten ~46 px ebenfalls ruhig bleiben (Fußzeile mit kleiner Schrift).

#### Aufbau von oben nach unten (Reihenfolge im Flex-Container)
1. **Safe-Zone-Spacer** — Höhe 170 px, kein Inhalt.
2. **Kopfzeile** — `padding: 6px 68px 0`, `flex`, `space-between`, vertikal zentriert.
   - Links: Radar-Logo (50×50 px) + Wortmarke `RENDITE RADAR`
     (Archivo 900, 27 px, letter-spacing 0.03em, `#fff`), Abstand 16 px.
     - Logo-Aufbau (rein per CSS, keine Bilddatei): `position: relative` 50×50;
       darin (a) Kreis `inset: 0`, `border: 4px solid #fff`, `border-radius: 50%`,
       `opacity: .3`; (b) Kreis `inset: 13px`, gleiche Border, `opacity: .55`;
       (c) Punkt `top: 5px; right: 5px`, 14×14 px, Accent-Farbe, `border-radius: 50%`.
   - Rechts: Badge `MEILENSTEIN` — Archivo 800, 21 px, letter-spacing 0.16em,
     Textfarbe = Accent, `border: 2px solid` Accent, `padding: 9px 18px`,
     `border-radius: 999px`, transparenter Hintergrund.
3. **Hero-Block** — `padding: 74px 68px 0`, zentriert (`flex column`, `align-items: center`,
   `text-align: center`).
   - Eyebrow: `Geknackt` — Archivo 800, 30 px, letter-spacing 0.24em, uppercase,
     `rgba(255,255,255,0.5)`.
   - **Große Zahl** (z. B. `1.000`), `margin-top: 18px`, zwei übereinanderliegende Kopien:
     - Hintere Kopie (nur Deko, `aria-hidden`): `position: absolute`, Archivo 900, 300 px,
       `line-height: .8`, letter-spacing -0.05em, `color: transparent`,
       `-webkit-text-stroke: 3px rgba(255,255,255,0.16)`, `transform: translate(14px, 14px)`.
     - Vordere Kopie: `position: relative`, gleiche Typo, `color: #fff`.
     - Zahlenformat: deutsche Tausender-Trennung (`1.000`, `2.500`) —
       `Number(n).toLocaleString('de-DE')`.
   - **FOLLOWER-Zeile**, `margin-top: 34px`, `flex`, `gap: 22px`, zentriert:
     Balken 70×4 px (Accent, radius 2) — Text `FOLLOWER` (Archivo 900, 60 px,
     letter-spacing 0.06em, Accent) — Balken 70×4 px.
4. **Dank-Block** — `padding: 66px 68px 0`, zentriert.
   - Headline: `Ihr seid die Besten!` — Archivo 900, 78 px, line-height 1.02,
     letter-spacing -0.025em, `#fff`.
   - Text, `margin-top: 22px`, Archivo 600, 30 px, line-height 1.45,
     `rgba(255,255,255,0.68)`, `text-wrap: pretty`, **fester Zeilenumbruch** nach Satz 1:
     `Danke für euer Vertrauen, jedes Like und jede Nachricht.` `<br>`
     `Ihr macht Rendite Radar zu dem, was es ist.`
5. **Spacer** — feste Höhe 44 px (rückt die beiden Boxen bewusst nach oben).
6. **Karte „Nächstes Ziel"** — `margin: 0 68px`, `background: rgba(255,255,255,0.06)`,
   `border: 2px solid rgba(255,255,255,0.1)`, `border-radius: 30px`, `padding: 34px 38px`.
   - Kopfzeile: `flex`, `space-between`, `align-items: flex-end`, `margin-bottom: 20px`
     - Links `NÄCHSTES ZIEL` — Archivo 800, 24 px, letter-spacing 0.1em, uppercase,
       `rgba(255,255,255,0.5)`.
     - Rechts Zielzahl — Archivo 900, 54 px, line-height 1, Accent.
   - Fortschrittsbalken: Track 26 px hoch, `border-radius: 999px`,
     `background: rgba(255,255,255,0.1)`, `overflow: hidden`;
     Füllung absolut positioniert, `width: <pct>%`, Accent, `border-radius: 999px`.
   - Darunter, `margin-top: 16px`: `Nur noch {fehlende} bis {ziel} – das schaffen wir!`
     Archivo 800, 26 px, `#fff`.
7. **CTA-Karte** — `margin: 22px 68px 0`, Hintergrund = Accent, `border-radius: 30px`,
   `padding: 34px 38px`, `flex`, `gap: 28px`, vertikal zentriert.
   - Icon-Kachel 84×84 px, `border-radius: 24px`, `background: rgba(255,255,255,0.2)`,
     darin Share-Icon 44×44 px (Stroke `#fff`, `stroke-width: 2.5`, round caps/joins;
     Pfade: `M4 12v7a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-7`, `M12 16V3`, `M7 8l5-5 5 5`).
   - Titel `Teilt diese Story!` — Archivo 900, 42 px, line-height 1.08, `#fff`.
   - Text, `margin-top: 8px` — Archivo 600, 26 px, line-height 1.38,
     `rgba(255,255,255,0.9)`: `Sendet den Kanal an jemanden, der Aktienanalysen liebt.`
8. **Flexibler Spacer** (`flex: 1`) — schiebt die Fußzeile an den unteren Rand.
9. **Fußzeile** — `padding: 26px 68px 46px`, `flex`, `space-between`, vertikal zentriert.
   - Links: `Keine Anlageberatung · Danke fürs Dabeisein` — Archivo 600, 22 px,
     `rgba(255,255,255,0.4)`.
   - Rechts: `@rendite.radar.official` — Archivo 700, 22 px, `rgba(255,255,255,0.5)`.

#### Dekorative Bühne (ein SVG, `position: absolute; inset: 0`, hinter allem)
`viewBox="0 0 1080 1920"`, `preserveAspectRatio="none"`. Reihenfolge:
1. **Glow**: Rechteck über die volle Fläche, gefüllt mit `radialGradient`
   (`cx: 50%`, `cy: 36%`, `r: 55%`): Accent bei 0 % mit `stop-opacity .42`,
   Accent bei 60 % mit `.08`, Accent bei 100 % mit `0`.
2. **Radar-Ringe** um Zentrum `cx = 540`, `cy = 700`, Radien `230, 340, 460, 590, 730`,
   `fill: none`, `stroke: #fff`, `stroke-width: 2.5`,
   Deckkraft `0.09 − index × 0.012` (also .090/.078/.066/.054/.042).
3. **Konfetti** — 14 feste Formen (keine Zufallswerte, damit Exporte reproduzierbar sind).
   Jede dritte Form (Index 0, 3, 6, 9, 12) in Accent mit `opacity .65`, alle anderen
   in `#fff` mit `opacity .3`. Liste `[x, y, Typ, s, Rotation]`:
   `[120,380,sq,22,12] [960,430,dot,14,0] [180,620,plus,26,-18] [925,660,sq,18,-8]`
   `[90,900,dot,11,0] [995,950,plus,22,14] [150,1120,sq,16,24] [935,1160,dot,13,0]`
   `[250,300,dot,9,0] [830,320,sq,13,-14] [60,520,plus,18,8] [1010,560,sq,15,20]`
   `[300,1215,plus,20,-10] [790,1240,dot,10,0]`
   - `dot`: Kreis mit Radius `s`.
   - `sq`: Rechteck `x-s, y-s`, Kantenlänge `2s`, `rx: 4`, um `Rotation` gedreht.
   - `plus`: zwei Linien (horizontal und vertikal, je Länge `2s`), `stroke-width: 6`,
     round caps, um `Rotation` gedreht.
4. **Kurskurve unten** (Marken-Bezug): Punkte
   `(-40,1830) (190,1755) (400,1805) (640,1680) (850,1730) (1120,1590)`.
   - Fläche: `polygon` von `0,1920` über die Punkte zu `1080,1920`, Accent, `opacity .14`.
   - Linie: `polyline`, Accent, `stroke-width: 9`, round join/cap, `opacity .5`.

## Interactions & Behavior
Statische Grafik — keine Klick- oder Hover-Zustände, keine Animation, kein Responsive-Verhalten.
Das Format ist fix 1080×1920. Alle Textfelder sind im Prototyp `contenteditable`; das ist
nur ein Authoring-Komfort und muss **nicht** nachgebaut werden.

Redaktioneller Ablauf beim Posten:
1. Meilenstein, nächstes Ziel und aktuellen Follower-Stand setzen.
2. PNG (1080×1920) rendern.
3. Als Instagram-Story posten.

## State Management
Kein UI-State. Drei Eingabewerte (Props/CLI-Argumente/ENV) steuern die gesamte Karte:

| Name | Typ | Default | Bedeutung |
|---|---|---|---|
| `meilenstein` | number | `1000` | Erreichter Meilenstein — die große Zahl |
| `naechstesZiel` | number | `meilenstein × 2` | Nächstes Ziel (Karte + CTA-Text) |
| `aktuellerStand` | number | `meilenstein` | Tatsächlicher Follower-Stand für den Balken |
| `accentColor` | string | `#0a7dd4` | Akzentfarbe |

Abgeleitete Werte:
- `pct = clamp(round(aktuellerStand / naechstesZiel × 100), 5, 100)` → Balkenbreite in %.
  (Untergrenze 5 %, damit der Balken nie unsichtbar wirkt.)
- `fehlende = max(0, naechstesZiel − aktuellerStand)`.
- Alle drei Zahlen in der Ausgabe mit `toLocaleString('de-DE')` formatieren.

## Design Tokens

**Farben**
| Token | Wert | Verwendung |
|---|---|---|
| Bühne/Hintergrund | `#0c1512` | Story-Hintergrund |
| Accent (Default) | `#0a7dd4` | Glow, Konfetti, FOLLOWER, Zielzahl, Balken, CTA-Fläche, Kurve |
| Accent-Alternativen | `#0a9d5f`, `#c9a227`, `#e0641e` | freigegebene Varianten |
| Weiß | `#ffffff` | Zahl, Headlines, Icon |
| Weiß 68 % | `rgba(255,255,255,0.68)` | Dank-Text |
| Weiß 55/50/40 % | `rgba(255,255,255,0.55 / 0.5 / 0.4)` | Logo-Ring, Labels, Fußzeile |
| Weiß 20 % | `rgba(255,255,255,0.2)` | Icon-Kachel in der CTA |
| Weiß 16 % | `rgba(255,255,255,0.16)` | Outline der Deko-Zahl |
| Weiß 10 % | `rgba(255,255,255,0.1)` | Balken-Track, Kartenrahmen |
| Weiß 6 % | `rgba(255,255,255,0.06)` | Karten-Hintergrund „Nächstes Ziel" |

**Typografie** — eine Familie: **Archivo** (Google Fonts, Gewichte 500/600/700/800/900).
Fallback `system-ui, sans-serif`.
| Element | Größe | Gewicht | Weitere Angaben |
|---|---|---|---|
| Große Zahl | 300 px | 900 | line-height .8, letter-spacing -0.05em |
| „Ihr seid die Besten!" | 78 px | 900 | line-height 1.02, letter-spacing -0.025em |
| FOLLOWER | 60 px | 900 | letter-spacing 0.06em |
| Zielzahl | 54 px | 900 | line-height 1 |
| CTA-Titel | 42 px | 900 | line-height 1.08 |
| Dank-Text | 30 px | 600 | line-height 1.45 |
| Eyebrow „Geknackt" | 30 px | 800 | letter-spacing 0.24em, uppercase |
| Wortmarke | 27 px | 900 | letter-spacing 0.03em |
| „Nur noch …", CTA-Text | 26 px | 800 / 600 | line-height 1.38 (CTA-Text) |
| Label „Nächstes Ziel" | 24 px | 800 | letter-spacing 0.1em, uppercase |
| Fußzeile | 22 px | 600 / 700 | |
| Badge „MEILENSTEIN" | 21 px | 800 | letter-spacing 0.16em |

**Abstände** — horizontaler Seitenrand durchgehend **68 px**.
Vertikal: Safe-Zone 170 · Kopf→Hero 74 · Hero→Dank 66 · Dank→Boxen 44 ·
Box→CTA 22 · Fußzeile `26px … 46px`. Innenabstände: Karten `34px 38px`, CTA `34px 38px`.

**Radien** — 999 px (Badge, Balken) · 30 px (beide Karten) · 24 px (Icon-Kachel) ·
4 px (Konfetti-Quadrate) · 2 px (FOLLOWER-Balken) · 50 % (Logo-Kreise, Punkte).

**Schatten** — keine. Tiefe entsteht ausschließlich über Glow, Transparenzen und die
versetzte Outline-Zahl.

## Assets
Keine Bilddateien. Alles ist Text, CSS und inline-SVG:
- Radar-Logo: drei CSS-Elemente (siehe Kopfzeile).
- Share-Icon: inline-SVG, Pfade oben angegeben.
- Deko-Bühne: ein inline-SVG, vollständig oben spezifiziert.
- Schrift: Archivo von Google Fonts —
  `https://fonts.googleapis.com/css2?family=Archivo:wght@500;600;700;800;900&display=swap`
  (beim Rendern unbedingt auf `document.fonts.ready` warten, sonst bricht die Typo).

## Export (PNG 1080×1920)
Empfohlener, robuster Weg mit Playwright/Puppeteer:
1. HTML laden, Viewport 1080×1920, `deviceScaleFactor: 1`.
2. Auf `document.fonts.ready` warten.
3. Das Story-Element (`#story-milestone2`) per `elementHandle.screenshot()` als PNG
   aufnehmen — nicht den ganzen Viewport, damit die Kanten exakt 1080×1920 bleiben.
4. Ergebnis prüfen: exakt 1080×1920 px, Fußzeile vollständig sichtbar, kein Beschnitt.

Beim Nachbau in einem Framework gilt dasselbe: Der Wrapper muss **exakt** 1080×1920 px
groß sein und `overflow: hidden` haben; keine Viewport-Einheiten verwenden.

## Files
- `Rendite Radar Story-Milestone v2.dc.html` — die Design-Referenz. Öffnet direkt im
  Browser. Das Story-Element trägt die id `story-milestone2`. Markup steht im
  `<x-dc>`-Block, die abgeleiteten Werte (Zahlenformat, Balkenbreite, Deko-SVG)
  im `<script data-dc-script>`-Block darunter.

## Verwandte Vorlagen (gleiches Designsystem, nicht Teil dieses Handoffs)
Im Projekt existieren weitere Stories im selben Look (Aktienanalyse-Card, Watchlist,
Quartalszahlen, Bio-Hinweis). Gemeinsame Regeln: 1080×1920, 170 px Safe-Zone oben,
Radar-Logo plus Wortmarke oben links, Kategorie-Badge oben rechts, Fußzeile mit
Disclaimer links und `@rendite.radar.official` rechts, Archivo als einzige Schrift.
