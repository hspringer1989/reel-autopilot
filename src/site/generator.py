"""Static 'Link in Bio' site: a clean gallery archive of the daily stock analyses
(story cards) that otherwise only live 24h in Instagram Stories. Rebuilt from the DB —
grouped by date, newest first. The self-contained story-card image is the analysis;
each card adds only a slim caption (name · ticker · ampel · Fazit).
Pure static HTML/CSS (nginx serves config.SITE_DIR at the domain).

Channel-neutral: every brand, text and legal value comes from the channel profile
(SITE_* keys, see channels/_template/profile.py), the palette from PROFILE.PALETTE."""
import html
import json
import shutil
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger
from sqlalchemy import select

import config
from src.storage.database import StoryRow, session_scope

_MONTHS = ["", "Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
           "August", "September", "Oktober", "November", "Dezember"]
_P = config.PROFILE
# Only show analyses from this date on (older cards may use a pre-redesign look).
# trade_date is an ISO "YYYY-MM-DD" string, so lexicographic >= is chronological.
_SITE_MIN_DATE = _P.SITE_MIN_DATE


def _hex(key: str) -> str:
    """Brand palette colour as a CSS hex string, so the site matches the cards."""
    r, g, b = _P.PALETTE[key]
    return f"#{r:02x}{g:02x}{b:02x}"


def _year() -> int:
    """Copyright year — read at build time, so the footer never goes stale."""
    return datetime.now(timezone.utc).year


def _fmt_date(d: str) -> str:
    try:
        y, m, day = d.split("-")
        return f"{int(day)}. {_MONTHS[int(m)]} {y}"
    except Exception:  # noqa: BLE001
        return d


def _dot(score: float | None) -> str:
    if score is None:
        return "#9ca3af"
    if score >= 0.6:
        return "#16a34a"
    if score >= 0.45:
        return "#eab308"
    return "#dc2626"


def _esc(x) -> str:
    return html.escape(str(x or ""))


def _collect() -> list[dict]:
    with session_scope() as session:
        rows = session.execute(
            select(StoryRow).where(
                StoryRow.kind.in_(("candidate", "trend")),
                StoryRow.status == "published",
                StoryRow.trade_date >= _SITE_MIN_DATE,
            ).order_by(StoryRow.trade_date.desc(), StoryRow.id.desc())
        ).scalars().all()
        items: list[dict] = []
        for r in rows:
            try:
                aj = json.loads(r.analysis_json or "{}")
            except Exception:  # noqa: BLE001
                aj = {}
            m = aj.get("metrics", {}) or {}
            items.append({
                "id": r.id,
                "date": r.trade_date,
                "image_path": r.image_path,
                "ticker": r.ticker or m.get("ticker", ""),
                "name": m.get("name", "") or r.ticker,
                "sector": m.get("sector", ""),
                "tech": m.get("tech_score"),
                "fund": m.get("fund_score"),
                "overall": aj.get("overall_text", ""),
                "chart": aj.get("chart_text", ""),
                "fundamental": aj.get("fundamental_text", ""),
                "currency": m.get("currency", ""),
                "entry": aj.get("entry"),
                "stop": aj.get("stop_loss"),
                "take": aj.get("take_profit"),
                "is_trend": r.kind == "trend",
            })
    return items


def _card_html(it: dict) -> str:
    trend = '<span class="trend">TREND</span>' if it["is_trend"] else ""
    parts = []
    if it["overall"]:
        parts.append(f'<p><b>Fazit:</b> {_esc(it["overall"])}</p>')
    if it["chart"]:
        parts.append(f'<p><b>Charttechnik:</b> {_esc(it["chart"])}</p>')
    if it["fundamental"]:
        parts.append(f'<p><b>Fundamental:</b> {_esc(it["fundamental"])}</p>')
    if it["entry"] and it["stop"] and it["take"]:
        try:
            parts.append(f'<p class="lv"><span>Referenz {float(it["entry"]):.2f}</span>'
                         f'<span>Stop {float(it["stop"]):.2f}</span>'
                         f'<span>Ziel {float(it["take"]):.2f} {_esc(it["currency"])}</span></p>')
        except Exception:  # noqa: BLE001
            pass
    details = ""
    if parts:
        details = ('<details class="det"><summary>Analyse lesen</summary>'
                   f'<div class="dbody">{"".join(parts)}</div></details>')
    return f"""      <article class="card" data-q="{_esc(it['name'])} {_esc(it['ticker'])} {_esc(it['sector'])}">
        <a class="thumb" href="cards/{it['id']}.jpg" target="_blank" rel="noopener" aria-label="Analyse {_esc(it['name'])} vergrößern">
          <img loading="lazy" src="cards/{it['id']}.jpg" alt="Aktien-Analyse {_esc(it['name'])} ({_esc(it['ticker'])})"></a>
        <div class="cap">
          <div class="row">
            <span class="nm">{_esc(it['name'])} <b>{_esc(it['ticker'])}</b>{trend}</span>
            <span class="dots" title="Chart · Fundamental">
              <i style="background:{_dot(it['tech'])}"></i><i style="background:{_dot(it['fund'])}"></i></span>
          </div>
          {details}
        </div>
      </article>"""


def _shell(inner: str, title: str, desc: str, home: bool) -> str:
    og_image = _P.SITE_URL.rstrip("/") + "/logo.png"
    # Rechtsseiten können extern liegen (z. B. zentral beim Betreiber-Gewerbe);
    # ohne Profil-Key bleiben es die lokal mitkopierten Seiten.
    privacy_url = getattr(_P, "SITE_PRIVACY_URL", "") or "/datenschutz"
    terms_url = getattr(_P, "SITE_TERMS_URL", "") or "/nutzungsbedingungen"
    top = "" if home else (
        '<header class="bar"><a class="bar-logo" href="/">'
        f'<img src="logo.png" width="34" height="34" alt="{_esc(_P.SITE_BRAND)}">'
        f'<span>{_esc(_P.SITE_BRAND)}</span></a></header>')
    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{desc}">
<meta property="og:title" content="{title}">
<meta property="og:image" content="{og_image}">
<style>
  :root{{--blue:{_hex('BLUE')};--navy:{_hex('BG')};--ink:#16202e;--muted:#667085;--bg:#eef2f6;--card:#fff;--line:#e2e8f0}}
  *{{box-sizing:border-box}}
  html{{scroll-behavior:smooth}}
  body{{margin:0;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:var(--ink);background:var(--bg);line-height:1.5}}
  a{{color:var(--blue)}}
  .wrap{{max-width:1140px;margin:0 auto;padding:0 16px}}
  /* hero — logo left + text right on desktop, stacked+centered on mobile */
  .hero{{position:relative;overflow:hidden;background:linear-gradient(120deg,var(--blue),var(--navy));color:#fff;padding:26px 0 34px}}
  .hero-in{{display:flex;align-items:center;gap:30px;text-align:left}}
  .hero .logo{{width:168px;height:168px;border-radius:30px;box-shadow:0 14px 40px rgba(0,0,0,.4);flex:0 0 auto}}
  .hero-txt{{flex:1;min-width:0}}
  .hero .tag{{letter-spacing:.2em;font-weight:800;font-size:.8rem;opacity:.9;margin:0 0 .35rem;text-transform:uppercase}}
  .hero h1{{font-size:2.3rem;line-height:1.1;margin:.1rem 0 .5rem;font-weight:800}}
  .hero .sub{{max-width:640px;margin:0;opacity:.95;font-size:1.02rem}}
  .hero .disc{{font-size:.85rem;opacity:.8;margin:.5rem 0 0}}
  .hero .ig{{display:inline-block;margin-top:14px;background:#fff;color:var(--navy);font-weight:800;text-decoration:none;padding:.5rem 1.2rem;border-radius:999px;box-shadow:0 6px 18px rgba(0,0,0,.18)}}
  .hero .motif{{position:absolute;left:0;right:0;bottom:-1px;width:100%;height:48px;display:block;pointer-events:none}}
  @media(max-width:660px){{
    .hero-in{{flex-direction:column;text-align:center;gap:14px}}
    .hero .logo{{width:150px;height:150px}}
    .hero .sub{{margin:0 auto}}
    .hero h1{{font-size:1.75rem}}
  }}
  /* sticky filter */
  .tools{{position:sticky;top:0;z-index:5;background:rgba(238,242,246,.92);backdrop-filter:blur(6px);border-bottom:1px solid var(--line);padding:12px 16px}}
  .toolbar{{display:flex;flex-wrap:wrap;gap:8px;width:min(760px,100%);margin:0 auto;align-items:center}}
  #filter{{flex:1 1 220px;min-width:170px;padding:.7rem 1rem;border:1px solid var(--line);border-radius:12px;font-size:1rem;background:#fff}}
  .tools select{{flex:0 0 auto;padding:.7rem .7rem;border:1px solid var(--line);border-radius:12px;font-size:1rem;background:#fff;color:var(--ink);cursor:pointer}}
  @media(max-width:520px){{#filter{{flex:1 1 100%}} .tools select{{flex:1 1 45%}}}}
  /* day sections */
  .day{{margin-top:26px}}
  .day h2{{display:inline-block;background:var(--navy);color:#fff;font-size:.95rem;font-weight:800;letter-spacing:.02em;padding:.35rem .8rem;border-radius:10px;margin:0 0 6px}}
  .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(290px,340px));gap:18px;margin-top:8px;justify-content:center}}
  .card{{background:var(--card);border:1px solid var(--line);border-radius:18px;overflow:hidden;display:flex;flex-direction:column;transition:transform .12s,box-shadow .12s}}
  .card:hover{{transform:translateY(-3px);box-shadow:0 10px 26px rgba(12,36,64,.14)}}
  .thumb{{display:block}}
  .thumb img{{width:100%;display:block;aspect-ratio:9/16;object-fit:cover;background:#0c2440}}
  .cap{{padding:12px 15px 14px}}
  .cap .row{{display:flex;align-items:center;justify-content:space-between;gap:8px}}
  .nm{{font-weight:700;font-size:1.02rem}}
  .nm b{{color:var(--blue);font-size:.85rem;margin-left:.25rem}}
  .trend{{background:var(--blue);color:#fff;font-size:.6rem;font-weight:800;letter-spacing:.06em;padding:.1rem .4rem;border-radius:6px;margin-left:.35rem;vertical-align:middle}}
  .dots{{white-space:nowrap;flex:0 0 auto}}
  .dots i{{display:inline-block;width:11px;height:11px;border-radius:50%;margin-left:5px;vertical-align:middle}}
  .det{{margin-top:.6rem;border-top:1px solid var(--line);padding-top:.55rem}}
  .det>summary{{cursor:pointer;list-style:none;color:var(--blue);font-weight:700;font-size:.9rem;display:flex;align-items:center;gap:.35rem;user-select:none}}
  .det>summary::-webkit-details-marker{{display:none}}
  .det>summary::after{{content:"▾";font-size:.8rem;transition:transform .15s}}
  .det[open]>summary::after{{transform:rotate(180deg)}}
  .det[open]>summary{{margin-bottom:.4rem}}
  .dbody p{{margin:.45rem 0;font-size:.9rem;line-height:1.5;color:#3a4756}}
  .dbody p b{{color:var(--navy)}}
  .lv{{display:flex;flex-wrap:wrap;gap:.3rem .8rem;font-size:.82rem;color:var(--muted)}}
  .lv span{{white-space:nowrap}}
  .empty{{text-align:center;color:var(--muted);padding:50px 0}}
  /* footer */
  footer{{background:var(--navy);color:#c3ccd8;text-align:center;padding:30px 16px;margin-top:40px;font-size:.86rem}}
  footer a{{color:#cdd6e2;margin:0 .3rem}}
  .legal{{max-width:760px;margin:0 auto;padding:34px 20px 10px}}
  .legal h1{{color:var(--navy)}}
  .bar{{background:var(--navy);padding:10px 16px}}
  .bar-logo{{display:flex;align-items:center;gap:9px;color:#fff;text-decoration:none;font-weight:800;max-width:1140px;margin:0 auto}}
  .bar-logo img{{border-radius:8px}}
</style>
</head>
<body>
{top}
{inner}
<footer>
  <p>{_P.SITE_FOOTER_DISCLAIMER}</p>
  <p><a href="{privacy_url}">Datenschutz</a> · <a href="{terms_url}">Nutzungsbedingungen</a> · <a href="/impressum">Impressum</a> · <a href="{_P.SITE_IG_URL}">Instagram</a></p>
  <p>© {_year()} {_esc(_P.SITE_BRAND)}</p>
</footer>
</body>
</html>"""


def _render_index(items: list[dict]) -> str:
    by_date: dict[str, list[dict]] = defaultdict(list)
    for it in items:
        by_date[it["date"]].append(it)
    sections = []
    for d in sorted(by_date, reverse=True):
        cards = "\n".join(_card_html(it) for it in by_date[d])
        sections.append(
            f'      <section class="day" data-year="{d[:4]}" data-month="{d[5:7]}" data-day="{d[8:10]}">'
            f'<h2>{_fmt_date(d)}</h2>\n'
            f'        <div class="grid">\n{cards}\n        </div></section>')
    body = "\n".join(sections) if sections else '      <p class="empty">Noch keine Analysen veröffentlicht.</p>'

    # Filter dropdowns: only years, months and days that actually have analyses.
    years = sorted({d[:4] for d in by_date}, reverse=True)
    months = sorted({d[5:7] for d in by_date})
    days = sorted({d[8:10] for d in by_date})
    year_opts = '<option value="">Alle Jahre</option>' + "".join(
        f'<option value="{y}">{y}</option>' for y in years)
    month_opts = '<option value="">Alle Monate</option>' + "".join(
        f'<option value="{mm}">{_MONTHS[int(mm)]}</option>' for mm in months)
    day_opts = '<option value="">Alle Tage</option>' + "".join(
        f'<option value="{dd}">{int(dd)}.</option>' for dd in days)
    inner = f"""  <header class="hero">
    <div class="wrap hero-in">
      <img class="logo" src="logo.png" alt="{_esc(_P.SITE_BRAND)} — {_esc(_P.SITE_TAGLINE)}">
      <div class="hero-txt">
        <p class="tag">{_esc(_P.SITE_TAGLINE)}</p>
        <h1>{_esc(_P.SITE_HEADLINE)}</h1>
        <p class="sub">{_P.SITE_INTRO}</p>
        <p class="disc">{_P.SITE_HERO_DISCLAIMER}</p>
        <a class="ig" href="{_P.SITE_IG_URL}" target="_blank" rel="noopener">{_esc(_P.SITE_IG_CTA)}</a>
      </div>
    </div>
    <svg class="motif" viewBox="0 0 1200 80" preserveAspectRatio="none" aria-hidden="true"><polyline points="0,72 220,52 380,62 620,26 820,40 1040,10 1200,20" fill="none" stroke="rgba(255,255,255,.5)" stroke-width="5"/></svg>
  </header>
  <div class="tools"><div class="toolbar">
    <input id="filter" placeholder="{_esc(_P.SITE_SEARCH_HINT)}" oninput="__apply()">
    <select id="fyear" onchange="__apply()" aria-label="Nach Jahr filtern">{year_opts}</select>
    <select id="fmonth" onchange="__apply()" aria-label="Nach Monat filtern">{month_opts}</select>
    <select id="fday" onchange="__apply()" aria-label="Nach Tag filtern">{day_opts}</select>
  </div></div>
  <main class="wrap">
{body}
    <p class="empty" id="noRes" style="display:none">Keine Analysen für diese Auswahl.</p>
  </main>
  <script>
    function __apply(){{
      var q=(document.getElementById('filter').value||'').trim().toLowerCase();
      var y=document.getElementById('fyear').value, m=document.getElementById('fmonth').value;
      var dd=document.getElementById('fday').value, any=false;
      document.querySelectorAll('.day').forEach(function(d){{
        var okd=(y===''||d.dataset.year===y)&&(m===''||d.dataset.month===m)&&(dd===''||d.dataset.day===dd), anyc=false;
        d.querySelectorAll('.card').forEach(function(c){{
          var show=okd&&c.dataset.q.toLowerCase().includes(q);
          c.style.display=show?'':'none'; if(show)anyc=true;
        }});
        d.style.display=anyc?'':'none'; if(anyc)any=true;
      }});
      var n=document.getElementById('noRes'); if(n)n.style.display=any?'none':'';
    }}
  </script>"""
    return _shell(inner, f"{_P.SITE_BRAND} — Analysen-Archiv", _P.SITE_META_DESC, home=True)


def _render_impressum() -> str:
    name = _esc(_P.SITE_IMPRESSUM_NAME)
    address = "<br>".join(_esc(line) for line in _P.SITE_IMPRESSUM_ADDRESS)
    mail = _esc(_P.SITE_IMPRESSUM_EMAIL)
    # Optionale Angaben für gewerbliche Betreiber: Inhaber (Einzelunternehmen mit
    # Geschäftsbezeichnung), Telefon, USt-IdNr. und ein vom Betreibernamen
    # abweichender MStV-Verantwortlicher (muss eine natürliche Person sein).
    owner = _esc(getattr(_P, "SITE_IMPRESSUM_OWNER", ""))
    phone = _esc(getattr(_P, "SITE_IMPRESSUM_PHONE", ""))
    vat = _esc(getattr(_P, "SITE_IMPRESSUM_VAT", ""))
    responsible = _esc(getattr(_P, "SITE_IMPRESSUM_RESPONSIBLE", "")) or owner or name

    holder = f"{name}<br>Inhaber: {owner}" if owner else name
    contact = f'E-Mail: <a href="mailto:{mail}">{mail}</a>'
    if phone:
        contact += f"<br>Telefon: {phone}"
    vat_html = (f'\n    <p><b>USt-IdNr. gemäß § 27a UStG:</b><br>{vat}</p>'
                if vat else "")
    inner = f"""  <div class="legal">
    <h1>Impressum</h1>
    <p>Angaben gemäß § 5 DDG / § 18 Abs. 2 MStV:</p>
    <p>{holder}<br>{address}</p>
    <p><b>Kontakt:</b><br>{contact}</p>{vat_html}
    <p><b>Verantwortlich für den Inhalt nach § 18 Abs. 2 MStV:</b><br>{responsible} (Anschrift wie oben)</p>
    <p style="color:#667085;font-size:.9rem">{_esc(_P.SITE_IMPRESSUM_NOTE)}</p>
    <p><a href="/">&larr; Zurück zu den Analysen</a></p>
  </div>"""
    return _shell(inner, f"Impressum — {_P.SITE_BRAND}",
                  f"Impressum von {_P.SITE_BRAND}.", home=False)


def build_site() -> int:
    """Regenerate the static site from the DB. Returns the number of analyses."""
    site = Path(config.SITE_DIR)
    cards = site / "cards"
    cards.mkdir(parents=True, exist_ok=True)

    items = _collect()
    for it in items:
        dst = cards / f"{it['id']}.jpg"
        if not dst.exists() and it["image_path"] and Path(it["image_path"]).exists():
            try:
                shutil.copyfile(it["image_path"], dst)
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"Card-Bild #{it['id']} nicht kopierbar: {exc}")

    logo_src = config.CHANNEL_DIR / "assets" / "brand" / "logo.png"
    if logo_src.exists():
        try:
            shutil.copyfile(logo_src, site / "logo.png")
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Logo nicht kopierbar: {exc}")

    (site / "index.html").write_text(_render_index(items), encoding="utf-8")
    (site / "impressum.html").write_text(_render_impressum(), encoding="utf-8")
    # Extern verlinkte Rechtsseiten (SITE_PRIVACY_URL/SITE_TERMS_URL) werden nicht
    # mehr lokal mitkopiert; die Datenlöschungs-Seite bleibt immer lokal (Meta-URL).
    legal_pages = ["datenloeschung.html"]
    if not getattr(_P, "SITE_PRIVACY_URL", ""):
        legal_pages.append("datenschutz.html")
    if not getattr(_P, "SITE_TERMS_URL", ""):
        legal_pages.append("nutzungsbedingungen.html")
    for name in legal_pages:
        src = Path(config.PUBLIC_MEDIA_DIR) / name
        if src.exists():
            try:
                shutil.copyfile(src, site / name)
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"Legal-Seite {name} nicht kopierbar: {exc}")

    days = len({it["date"] for it in items})
    logger.info(f"Website gebaut: {len(items)} Analysen an {days} Tagen → {site}")
    return len(items)
