"""Opener-Auswahl per Augenschein für die Reel-Automatik.

Bildet den Teil der Handarbeit nach, der bisher nur mit menschlichem Blick ging:
Pexels durchsuchen, Kandidaten als Kontaktbogen rendern, hinsehen, und den Clip
wählen, der hell ist, ein klares Motiv hat UND zum Thema passt.

Warum nicht einfach die hellste Datei nehmen: Helligkeit allein führt in die Irre.
Ein heller, sauberer Clip, auf dessen Laptop-Bildschirm ein Kleiderladen läuft, ist
für ein Reel über Technikpreise unbrauchbar — das war ein realer Fehlgriff. Umgekehrt
wurde ein Clip verworfen, dessen Poster ein "CLOSE"-Schild zeigte, während das Video
es nach 0,9 s auf "OPEN" dreht. Beide Fälle findet nur ein Blick auf bewegte Frames.

Deshalb prüft dieses Modul jeden Kandidaten an DREI über den Clip verteilten Frames
und lässt das Modell entscheiden.

⛔ Harte Regel des Users: "niemals der selbe opener, den wir schonmal hatten" — und
"derselbe" meint die MOTIVKLASSE, nicht die Clip-ID. Ein anderer Clip mit gleichem
Look zählt als Wiederholung. Die Historie kommt deshalb als Ausschlussliste in den
Prompt, zusätzlich zum ID-Filter.
"""
from __future__ import annotations

import io
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

import httpx
from loguru import logger
from PIL import Image

import config
from src.content.llm import LLMProvider, parse_json_response
from src.render.broll import _pick_file

_SYSTEM = """Du wählst das Startbild (Opener) für ein deutsches Finanz-Reel auf Instagram.
Der Opener ist zugleich das Vorschaubild im Profilraster und entscheidet, ob jemand
stehen bleibt.

Anforderungen, in dieser Reihenfolge:
1. BEDEUTUNG SCHLÄGT HELLIGKEIT. Würde jemand OHNE TON erahnen, worum es geht? Ein
   hübsches, aber themenfremdes Bild ist schlechter als ein schlichtes passendes.
2. HELL UND FARBIG. Dunkle, flaue oder graue Clips sind ausgeschlossen.
3. KLARER HERO. Ein Objekt, eine Person, ein Bauwerk oder ein Tier deutlich im Bild.
   Keine weiten Landschaften, nichts Abstraktes.
4. KEIN STÖRENDER TEXT IM BILD. Besonders keine sichtbaren Datumsangaben, keine
   Fremdsprachen-Beschilderung, die dem Thema widerspricht, keine dominanten Logos.
5. STIMMIG ÜBER DIE GANZE LÄNGE. Du siehst pro Kandidat drei Frames aus verschiedenen
   Momenten. Wenn sich die Aussage zwischen den Frames dreht (Schild klappt um,
   Szene wechselt), ist der Clip unbrauchbar.

Antworte ausschließlich mit diesem JSON:
{"pick": <Nummer des Kandidaten oder null>,
 "reason": "ein Satz, warum dieser",
 "rejected": {"<Nummer>": "kurzer Grund", ...}}
Setze "pick": null, wenn KEIN Kandidat die Anforderungen erfüllt — lieber neu suchen
als ein schlechtes Startbild."""


@dataclass
class OpenerChoice:
    video_id: int | None
    path: str | None
    reason: str = ""


def _cache_clip(video_id: int) -> str | None:
    """Portrait-Datei in den B-Roll-Cache laden; None wenn Pexels nichts Nutzbares hat."""
    cache = Path(config.BROLL_CACHE_DIR)
    for p in cache.glob(f"pexels_{video_id}_*.mp4"):
        return str(p)
    try:
        r = httpx.get(f"https://api.pexels.com/videos/videos/{video_id}",
                      headers={"Authorization": config.PEXELS_API_KEY}, timeout=30)
        r.raise_for_status()
        fl = _pick_file(r.json())
        target = cache / f"pexels_{video_id}_{fl['height']}.mp4"
        if not target.exists():
            target.write_bytes(
                httpx.get(fl["link"], timeout=180, follow_redirects=True).content)
        return str(target)
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"Clip {video_id} nicht ladbar: {exc}")
        return None


def _search(queries: list[str], exclude: set[int], per_query: int = 4) -> list[dict]:
    """Pexels-Kandidaten sammeln. Nur Portrait, nur ausreichend hohe Auflösung."""
    found: dict[int, dict] = {}
    for q in queries:
        try:
            r = httpx.get("https://api.pexels.com/videos/search",
                          headers={"Authorization": config.PEXELS_API_KEY},
                          params={"query": q, "orientation": "portrait",
                                  "per_page": per_query},
                          timeout=30)
            r.raise_for_status()
            for v in r.json().get("videos", []):
                if v["id"] in exclude or v["id"] in found:
                    continue
                if max((f.get("height") or 0) for f in v["video_files"]) < 1280:
                    continue
                found[v["id"]] = v
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"Pexels-Suche '{q}' fehlgeschlagen: {exc}")
    return list(found.values())


def _frames(path: str, count: int = 3) -> list[Image.Image]:
    """`count` Frames gleichmäßig über den Clip verteilt — deckt Wendungen auf, die
    ein einzelner Frame (oder das Pexels-Poster) verschweigt."""
    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", path],
            capture_output=True, text=True, check=True)
        duration = float(probe.stdout.strip() or 0)
    except Exception:  # noqa: BLE001
        duration = 0.0
    if duration <= 0:
        return []

    out: list[Image.Image] = []
    for i in range(count):
        # Ränder meiden: Anfang und Ende sind oft Ein-/Ausblenden
        t = duration * (0.15 + 0.7 * (i / max(count - 1, 1)))
        tmp = f"/tmp/opener_probe_{i}.jpg"
        try:
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.2f}",
                            "-i", path, "-frames:v", "1", tmp], check=True)
            out.append(Image.open(tmp).convert("RGB"))
        except Exception:  # noqa: BLE001
            continue
    return out


def _sheet(candidates: list[tuple[int, list[Image.Image]]]) -> bytes:
    """Kontaktbogen: eine Zeile je Kandidat, drei Frames nebeneinander, nummeriert."""
    from PIL import ImageDraw

    tw, th, label = 240, 427, 34
    rows = len(candidates)
    sheet = Image.new("RGB", (3 * tw, rows * (th + label)), (18, 18, 18))
    d = ImageDraw.Draw(sheet)
    for row, (_vid, frames) in enumerate(candidates):
        y = row * (th + label)
        for col, im in enumerate(frames[:3]):
            sheet.paste(im.resize((tw, th)), (col * tw, y))
        d.text((8, y + th + 8), f"Kandidat {row + 1}", fill=(255, 235, 90))
    buf = io.BytesIO()
    sheet.save(buf, format="JPEG", quality=82)
    return buf.getvalue()


def pick_opener(llm: LLMProvider, topic: str, queries: list[str],
                exclude_ids: set[int], history_note: str = "",
                max_candidates: int = 6) -> OpenerChoice:
    """Kandidaten suchen, als Kontaktbogen rendern, ansehen lassen, einen wählen.

    `exclude_ids` sind bereits verwendete Clip-IDs (harter Filter), `history_note`
    beschreibt die verbrauchten MOTIVKLASSEN in Prosa (weicher Filter im Prompt) —
    beides ist nötig, weil ein anderer Clip mit gleichem Look ebenfalls als
    Wiederholung zählt.
    """
    videos = _search(queries, exclude_ids)
    if not videos:
        logger.warning("Keine Opener-Kandidaten bei Pexels gefunden")
        return OpenerChoice(None, None, "keine Kandidaten gefunden")

    prepared: list[tuple[int, list[Image.Image]]] = []
    for v in videos:
        if len(prepared) >= max_candidates:
            break
        path = _cache_clip(v["id"])
        if not path:
            continue
        frames = _frames(path)
        if len(frames) >= 2:
            prepared.append((v["id"], frames))

    if not prepared:
        logger.warning("Kein Opener-Kandidat konnte geladen werden")
        return OpenerChoice(None, None, "kein Kandidat ladbar")

    user = (f"Thema des Reels: {topic}\n\n"
            f"{len(prepared)} Kandidaten, je drei Frames aus verschiedenen Momenten "
            f"desselben Clips (eine Zeile je Kandidat, von oben nach unten "
            f"durchnummeriert).\n")
    if history_note:
        user += (f"\nBEREITS VERBRAUCHTE MOTIVKLASSEN — ein Kandidat, der einer davon "
                 f"ähnelt, ist ausgeschlossen, auch wenn es ein anderer Clip ist:\n"
                 f"{history_note}\n")
    user += "\nWelchen Kandidaten nimmst du?"

    answer = parse_json_response(llm.judge_image(
        system=_SYSTEM, user=user, image_jpeg=_sheet(prepared),
        model=config.CLAUDE_MODEL, max_tokens=900, purpose="reel_opener_pick",
    ))
    if not isinstance(answer, dict):
        logger.warning("Opener-Auswahl lieferte kein JSON")
        return OpenerChoice(None, None, "Antwort unlesbar")

    pick = answer.get("pick")
    if answer.get("rejected"):
        logger.info(f"Opener verworfen: {json.dumps(answer['rejected'], ensure_ascii=False)}")
    if not isinstance(pick, int) or not 1 <= pick <= len(prepared):
        logger.info(f"Kein Opener-Kandidat überzeugt: {answer.get('reason', '')}")
        return OpenerChoice(None, None, str(answer.get("reason", "kein Kandidat passend")))

    vid = prepared[pick - 1][0]
    path = _cache_clip(vid)
    logger.info(f"Opener gewählt: {vid} — {answer.get('reason', '')}")
    return OpenerChoice(vid, path, str(answer.get("reason", "")))
