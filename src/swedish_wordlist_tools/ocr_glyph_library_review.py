from __future__ import annotations

import argparse
import base64
import html
import json
import re
from collections import defaultdict
from pathlib import Path

from PIL import Image


def _data_uri(path: Path) -> str:
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{data}"


def _decode_label(dirname: str) -> str:
    if dirname.startswith("u") and len(dirname) == 5:
        try:
            return chr(int(dirname[1:], 16))
        except ValueError:
            pass
    return dirname


def _label_from_filename(path: Path) -> str:
    raw = path.stem.split("-", 1)[0]
    return _decode_label(raw)


def _subnr_from_filename(path: Path) -> str | None:
    match = re.search(r"-sub([^-]+)-", path.name)
    return match.group(1) if match else None


def _load_sources(jsonl: Path | None) -> dict[str, dict[str, object]]:
    if jsonl is None:
        return {}
    result: dict[str, dict[str, object]] = {}
    with jsonl.open("r", encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            entry = json.loads(line)
            subnr = entry.get("subnr")
            if subnr is not None:
                result[str(subnr)] = entry
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a static visual review page for a mined SAOL glyph library.")
    parser.add_argument("library", type=Path)
    parser.add_argument("--style", choices=("italic", "bold", "roman"), help="Show only one style; default shows separate sections for every available style")
    parser.add_argument("--jsonl", type=Path, help="SAOL JSONL; enables direct links from each glyph to its source facsimile page")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--scale", type=int, default=8)
    args = parser.parse_args()

    sources = _load_sources(args.jsonl)
    styles = [args.style] if args.style else [s for s in ("bold", "italic", "roman") if (args.library / s).is_dir()]
    if not styles:
        raise SystemExit(f"No style directories found in {args.library}")

    style_sections: list[str] = []
    total = 0
    for style in styles:
        paths = sorted((args.library / style).glob("*.png"))
        if not paths:
            continue
        total += len(paths)
        groups: dict[str, list[Path]] = defaultdict(list)
        for path in paths:
            groups[_label_from_filename(path)].append(path)

        char_sections: list[str] = []
        for label in sorted(groups):
            cards: list[str] = []
            for path in groups[label]:
                with Image.open(path) as im:
                    width, height = im.size
                source_html = ""
                subnr = _subnr_from_filename(path)
                entry = sources.get(subnr or "")
                if entry:
                    source = entry.get("source")
                    page = entry.get("sidnr1")
                    word = entry.get("normaliserat_ord") or entry.get("ord") or ""
                    if isinstance(source, str) and source:
                        source_html = f'<a class="source" href="{html.escape(source, quote=True)}" target="_blank" rel="noopener">källsida {html.escape(str(page))} ↗</a><div class="sourceword">{html.escape(str(word))}</div>'
                cards.append(
                    '<figure class="card">'
                    f'<div class="frame"><img src="{_data_uri(path)}" alt="{html.escape(label)}"></div>'
                    f'<figcaption class="label">{html.escape(label)}</figcaption>'
                    f'<div class="stylebadge">{html.escape(style)}</div>'
                    f'<div class="dims">{width}×{height}px</div>{source_html}'
                    f'<div class="name">{html.escape(path.name)}</div>'
                    '</figure>'
                )
            char_sections.append(f'<section class="char"><h3>{html.escape(label)} <span>{len(cards)} mallar</span></h3><div class="grid">{"".join(cards)}</div></section>')
        style_sections.append(f'<section class="style"><h2>{html.escape(style).upper()}</h2>{"".join(char_sections)}</section>')

    doc = f'''<!doctype html>
<meta charset="utf-8">
<title>SAOL glyph library review</title>
<style>
:root{{--scale:{max(1, args.scale)};}}*{{box-sizing:border-box}}body{{font-family:system-ui,sans-serif;margin:24px;background:#f6f6f6;color:#161616}}h1{{margin-bottom:.25rem}}.intro{{max-width:950px;color:#444;margin-bottom:1.5rem}}.toolbar{{position:sticky;top:0;background:#f6f6f6e8;backdrop-filter:blur(6px);padding:.7rem 0;z-index:2}}input{{font:inherit;padding:.45rem .6rem;width:20rem;max-width:100%;border:1px solid #bbb;border-radius:6px}}.style{{margin:2rem 0 4rem;border-top:5px solid #222;padding-top:.5rem}}.style>h2{{font-size:32px;margin:.4rem 0 1.5rem}}.char{{margin:1.5rem 0 2.5rem}}h3{{border-bottom:1px solid #ccc;padding-bottom:.35rem}}h3 span{{font-size:.8rem;font-weight:400;color:#666}}.grid{{display:flex;flex-wrap:wrap;gap:12px}}.card{{margin:0;background:white;border:1px solid #ccc;border-radius:8px;padding:10px;width:180px;min-height:205px}}.frame{{height:92px;display:flex;align-items:center;justify-content:center;background:#eee;border:1px solid #bbb;overflow:hidden}}.frame img{{image-rendering:pixelated;transform:scale(var(--scale));transform-origin:center center}}.label{{font-size:28px;font-weight:700;text-align:center;line-height:1.1;margin-top:8px}}.stylebadge{{text-align:center;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.08em}}.dims{{text-align:center;color:#666;font-size:12px}}.source{{display:block;text-align:center;margin-top:7px;font-size:13px;font-weight:650}}.sourceword{{text-align:center;font-size:11px;color:#555;overflow-wrap:anywhere}}.name{{font-size:9px;color:#777;overflow-wrap:anywhere;margin-top:6px}}.hidden{{display:none!important}}
</style>
<h1>SAOL glyph library review</h1>
<p class="intro">{total} mallar. Fet, kursiv och rak stil visas i strikt separata huvudsektioner. Klicka på <b>källsida</b> under en mall för att öppna den ursprungliga SAOL-faksimilsidan och kontrollera utskärningen i sitt sammanhang.</p>
<div class="toolbar"><input id="filter" placeholder="Filtrera tecken, stil eller filnamn…"></div>
{''.join(style_sections)}
<script>const q=document.getElementById('filter');q.addEventListener('input',()=>{{const n=q.value.toLowerCase();document.querySelectorAll('.card').forEach(c=>c.classList.toggle('hidden',!c.innerText.toLowerCase().includes(n)));document.querySelectorAll('.char').forEach(s=>s.classList.toggle('hidden',![...s.querySelectorAll('.card')].some(c=>!c.classList.contains('hidden'))));document.querySelectorAll('.style').forEach(s=>s.classList.toggle('hidden',!s.querySelector('.card:not(.hidden)')));}});</script>
'''
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(doc, encoding="utf-8")
    print(args.out)
    print(f"templates={total} styles={','.join(styles)} source_links={'yes' if sources else 'no'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
