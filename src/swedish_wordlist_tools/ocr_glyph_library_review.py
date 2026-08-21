from __future__ import annotations

import argparse
import base64
import html
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


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a static visual review page for a mined SAOL glyph library."
    )
    parser.add_argument("library", type=Path, help="Glyph library root, e.g. /tmp/saol14-glyph-test5")
    parser.add_argument("--style", default="italic", choices=("italic", "bold", "roman"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--scale", type=int, default=8, help="CSS pixel zoom factor")
    args = parser.parse_args()

    style_dir = args.library / args.style
    paths = sorted(style_dir.glob("*.png"))
    if not paths:
        raise SystemExit(f"No PNG templates found in {style_dir}")

    groups: dict[str, list[Path]] = defaultdict(list)
    for path in paths:
        groups[_label_from_filename(path)].append(path)

    sections: list[str] = []
    for label in sorted(groups):
        cards: list[str] = []
        for path in groups[label]:
            with Image.open(path) as im:
                width, height = im.size
            cards.append(
                '<figure class="card">'
                f'<div class="frame"><img src="{_data_uri(path)}" alt="{html.escape(label)}"></div>'
                f'<figcaption class="label">{html.escape(label)}</figcaption>'
                f'<div class="dims">{width}×{height}px</div>'
                f'<div class="name">{html.escape(path.name)}</div>'
                '</figure>'
            )
        sections.append(
            f'<section id="char-{html.escape(label)}">'
            f'<h2>{html.escape(label)} <span>{len(cards)} mallar</span></h2>'
            f'<div class="grid">{"".join(cards)}</div>'
            '</section>'
        )

    doc = f'''<!doctype html>
<meta charset="utf-8">
<title>SAOL glyph library review — {html.escape(args.style)}</title>
<style>
:root{{--scale:{max(1, args.scale)};}}
*{{box-sizing:border-box}}
body{{font-family:system-ui,sans-serif;margin:24px;background:#f6f6f6;color:#161616}}
h1{{margin-bottom:.25rem}}
.intro{{max-width:900px;color:#444;margin-bottom:1.5rem}}
.toolbar{{position:sticky;top:0;background:#f6f6f6e8;backdrop-filter:blur(6px);padding:.7rem 0;z-index:2}}
input{{font:inherit;padding:.45rem .6rem;width:20rem;max-width:100%;border:1px solid #bbb;border-radius:6px}}
section{{margin:1.5rem 0 2.5rem}}
h2{{border-bottom:1px solid #ccc;padding-bottom:.35rem}}
h2 span{{font-size:.8rem;font-weight:400;color:#666}}
.grid{{display:flex;flex-wrap:wrap;gap:12px}}
.card{{margin:0;background:white;border:1px solid #ccc;border-radius:8px;padding:10px;width:170px;min-height:170px}}
.frame{{height:92px;display:flex;align-items:center;justify-content:center;background:#eee;border:1px solid #bbb;overflow:hidden}}
.frame img{{image-rendering:pixelated;transform:scale(var(--scale));transform-origin:center center}}
.label{{font-size:28px;font-weight:700;text-align:center;line-height:1.1;margin-top:8px}}
.dims{{text-align:center;color:#666;font-size:12px}}
.name{{font-size:9px;color:#777;overflow-wrap:anywhere;margin-top:6px}}
.hidden{{display:none!important}}
</style>
<h1>SAOL glyph library review</h1>
<p class="intro">Stil: <b>{html.escape(args.style)}</b>. Varje ruta ska visa endast glyphen som står under den. Den grå ytan är bara visningsbakgrund; PNG-cropen är uppskalad med nearest-neighbour/pixelated rendering. Om en ruta innehåller del av en grannbokstav, flera tecken eller tydligt avhuggen glyph är den mallen felcroppad.</p>
<div class="toolbar"><input id="filter" placeholder="Filtrera tecken eller filnamn…"></div>
{''.join(sections)}
<script>
const q = document.getElementById('filter');
q.addEventListener('input', () => {{
  const needle = q.value.toLowerCase();
  document.querySelectorAll('.card').forEach(card => {{
    card.classList.toggle('hidden', !card.innerText.toLowerCase().includes(needle));
  }});
  document.querySelectorAll('section').forEach(sec => {{
    const visible = [...sec.querySelectorAll('.card')].some(c => !c.classList.contains('hidden'));
    sec.classList.toggle('hidden', !visible);
  }});
}});
</script>
'''
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(doc, encoding="utf-8")
    print(args.out)
    print(f"templates={len(paths)} classes={len(groups)} style={args.style}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
