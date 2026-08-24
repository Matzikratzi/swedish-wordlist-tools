from __future__ import annotations

import argparse
import base64
import html
import json
import re
from collections import defaultdict
from io import BytesIO
from pathlib import Path

from PIL import Image


def _data_uri(path: Path) -> str:
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{data}"


def _image_data_uri(image: Image.Image) -> str:
    buf = BytesIO()
    image.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


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


def _load_template_sources(library: Path, manifest: Path | None = None) -> dict[str, dict[str, object]]:
    candidates: list[Path] = []
    if manifest is not None:
        candidates.append(manifest)
    else:
        preferred = library / "manifest-pages.json"
        if preferred.exists():
            candidates.append(preferred)
        candidates.extend(sorted(p for p in library.glob("manifest-pages*.json") if p not in candidates))
    for path in candidates:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        raw = data.get("template_sources", {})
        if isinstance(raw, dict) and raw:
            return raw
    return {}


def _context_for(meta: dict[str, object], pad_x: int = 150, pad_y: int = 55) -> tuple[str, list[int], list[int]] | None:
    bbox = meta.get("bbox")
    image_path = meta.get("column_image")
    if not isinstance(bbox, list) or len(bbox) != 4 or not isinstance(image_path, str):
        return None
    path = Path(image_path)
    if not path.exists():
        return None
    x, y, w, h = map(int, bbox)
    with Image.open(path) as im0:
        im = im0.convert("L")
        left = max(0, x - pad_x)
        top = max(0, y - pad_y)
        right = min(im.width, x + w + pad_x)
        bottom = min(im.height, y + h + pad_y)
        crop = im.crop((left, top, right, bottom))
    local_box = [x - left, y - top, w, h]
    origin = [left, top]
    return _image_data_uri(crop), local_box, origin


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a static visual review page for a mined SAOL glyph library.")
    parser.add_argument("library", type=Path)
    parser.add_argument("--style", choices=("italic", "bold", "roman"), help="Show only one style; default shows separate sections for every available style")
    parser.add_argument("--jsonl", type=Path, help="SAOL JSONL; enables source metadata from JSONL")
    parser.add_argument("--manifest", type=Path, help="Explicit mining manifest; enables source context and direct facsimile links")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--scale", type=int, default=8)
    args = parser.parse_args()

    sources = _load_sources(args.jsonl)
    template_sources = _load_template_sources(args.library, args.manifest)
    styles = [args.style] if args.style else [s for s in ("bold", "italic", "roman") if (args.library / s).is_dir()]
    if not styles:
        raise SystemExit(f"No style directories found in {args.library}")

    style_sections: list[str] = []
    total = 0
    source_contexts = 0
    facsimile_links = 0
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
                subnr = _subnr_from_filename(path)
                entry = sources.get(subnr or "")
                key = f"{style}/{path.name}"
                meta = template_sources.get(key, {})

                source_url = meta.get("source") if isinstance(meta, dict) else None
                source_page = meta.get("page") if isinstance(meta, dict) else None
                source_word = meta.get("expected_word") if isinstance(meta, dict) else None
                if not isinstance(source_url, str) or not source_url:
                    if entry:
                        source_url = entry.get("source")
                        source_page = entry.get("sidnr1")
                        source_word = entry.get("normaliserat_ord") or entry.get("ord") or source_word
                source_html = ""
                if isinstance(source_url, str) and source_url:
                    facsimile_links += 1
                    source_html = (
                        f'<a class="source" href="{html.escape(source_url, quote=True)}" target="_blank" rel="noopener">'
                        f'faksimil sida {html.escape(str(source_page or ""))} ↗</a>'
                        f'<div class="sourceword">{html.escape(str(source_word or ""))}</div>'
                    )

                context = _context_for(meta) if isinstance(meta, dict) else None
                review_html = ""
                if context:
                    source_contexts += 1
                    context_uri, box, origin = context
                    page = meta.get("page", "")
                    column = meta.get("column", "")
                    page_bbox = meta.get("page_bbox", "")
                    review_payload = html.escape(json.dumps({
                        "label": label,
                        "style": style,
                        "filename": path.name,
                        "page": page,
                        "column": column,
                        "context": context_uri,
                        "box": box,
                        "origin": origin,
                        "page_bbox": page_bbox,
                        "source": source_url or "",
                    }, ensure_ascii=False), quote=True)
                    review_html = f'<button class="review" data-review="{review_payload}">granska / rita box</button>'

                cards.append(
                    '<figure class="card">'
                    f'<div class="frame"><img src="{_data_uri(path)}" alt="{html.escape(label)}"></div>'
                    f'<figcaption class="label">{html.escape(label)}</figcaption>'
                    f'<div class="stylebadge">{html.escape(style)}</div>'
                    f'<div class="dims">{width}×{height}px</div>{review_html}{source_html}'
                    f'<div class="name">{html.escape(path.name)}</div>'
                    '</figure>'
                )
            char_sections.append(f'<section class="char"><h3>{html.escape(label)} <span>{len(cards)} mallar</span></h3><div class="grid">{"".join(cards)}</div></section>')
        style_sections.append(f'<section class="style"><h2>{html.escape(style).upper()}</h2>{"".join(char_sections)}</section>')

    doc = f'''<!doctype html>
<meta charset="utf-8">
<title>SAOL glyph library review</title>
<style>
:root{{--scale:{max(1, args.scale)};}}*{{box-sizing:border-box}}body{{font-family:system-ui,sans-serif;margin:24px;background:#f6f6f6;color:#161616}}h1{{margin-bottom:.25rem}}.intro{{max-width:950px;color:#444;margin-bottom:1.5rem}}.toolbar{{position:sticky;top:0;background:#f6f6f6e8;backdrop-filter:blur(6px);padding:.7rem 0;z-index:2}}input{{font:inherit;padding:.45rem .6rem;width:20rem;max-width:100%;border:1px solid #bbb;border-radius:6px}}.style{{margin:2rem 0 4rem;border-top:5px solid #222;padding-top:.5rem}}.style>h2{{font-size:32px;margin:.4rem 0 1.5rem}}.char{{margin:1.5rem 0 2.5rem}}h3{{border-bottom:1px solid #ccc;padding-bottom:.35rem}}h3 span{{font-size:.8rem;font-weight:400;color:#666}}.grid{{display:flex;flex-wrap:wrap;gap:12px}}.card{{margin:0;background:white;border:1px solid #ccc;border-radius:8px;padding:10px;width:190px;min-height:235px}}.frame{{height:92px;display:flex;align-items:center;justify-content:center;background:#eee;border:1px solid #bbb;overflow:hidden}}.frame img{{image-rendering:pixelated;transform:scale(var(--scale));transform-origin:center center}}.label{{font-size:28px;font-weight:700;text-align:center;line-height:1.1;margin-top:8px}}.stylebadge{{text-align:center;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.08em}}.dims{{text-align:center;color:#666;font-size:12px}}.source{{display:block;text-align:center;margin-top:7px;font-size:12px;font-weight:650}}.sourceword{{text-align:center;font-size:11px;color:#555;overflow-wrap:anywhere}}.review{{display:block;margin:7px auto 0;padding:4px 8px;font:inherit;font-size:12px;cursor:pointer}}.name{{font-size:9px;color:#777;overflow-wrap:anywhere;margin-top:6px}}.hidden{{display:none!important}}
#modal{{position:fixed;inset:0;background:#000b;z-index:20;display:none;align-items:center;justify-content:center;padding:20px}}#modal.open{{display:flex}}.modalbox{{background:white;border-radius:10px;padding:16px;max-width:96vw;max-height:96vh;overflow:auto}}.modalhead{{display:flex;gap:16px;align-items:center;justify-content:space-between;margin-bottom:10px}}.sourcecanvaswrap{{position:relative;display:inline-block;border:1px solid #555;background:white;cursor:crosshair}}#sourceimg{{display:block;image-rendering:pixelated;transform-origin:left top}}#overlay{{position:absolute;left:0;top:0;pointer-events:auto}}.coords{{font-family:ui-monospace,monospace;font-size:12px;white-space:pre-wrap;margin-top:8px}}.modalactions{{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px}}.modalactions button,.modalactions a{{padding:5px 9px}}.hint{{font-size:12px;color:#555;max-width:800px}}
</style>
<h1>SAOL glyph library review</h1>
<p class="intro">{total} mallar. Fet, kursiv och rak stil visas separat. <b>granska / rita box</b> visar ett större källutsnitt med vår box i rött. Dra med musen för att rita en egen grön box; koordinaterna kan kopieras. {source_contexts} mallar har lokal källkontext och {facsimile_links} har direktlänk till faksimilen.</p>
<div class="toolbar"><input id="filter" placeholder="Filtrera tecken, stil eller filnamn…"></div>
{''.join(style_sections)}
<div id="modal"><div class="modalbox"><div class="modalhead"><strong id="modaltitle"></strong><button id="close">stäng</button></div><p class="hint">Röd box = automatisk crop. Dra en ny box över exakt tecknet. Grön box = din manuella box. Koordinater anges i originalspaltens pixlar.</p><div class="sourcecanvaswrap"><img id="sourceimg"><canvas id="overlay"></canvas></div><div id="coords" class="coords"></div><div class="modalactions"><a id="facsimile" target="_blank" rel="noopener">öppna faksimil ↗</a><button id="copybox">kopiera manuell box</button><button id="resetbox">rensa manuell box</button></div></div></div>
<script>
const q=document.getElementById('filter');q.addEventListener('input',()=>{{const n=q.value.toLowerCase();document.querySelectorAll('.card').forEach(c=>c.classList.toggle('hidden',!c.innerText.toLowerCase().includes(n)));document.querySelectorAll('.char').forEach(s=>s.classList.toggle('hidden',![...s.querySelectorAll('.card')].some(c=>!c.classList.contains('hidden'))));document.querySelectorAll('.style').forEach(s=>s.classList.toggle('hidden',!s.querySelector('.card:not(.hidden)')));}});
const modal=document.getElementById('modal'), img=document.getElementById('sourceimg'), canvas=document.getElementById('overlay'), ctx=canvas.getContext('2d'), coords=document.getElementById('coords'), title=document.getElementById('modaltitle'), facsimile=document.getElementById('facsimile');
let payload=null, dragging=false, start=null, manual=null, zoom=4;
function draw(){{ctx.clearRect(0,0,canvas.width,canvas.height); if(!payload)return; const b=payload.box; ctx.strokeStyle='#d00';ctx.lineWidth=2;ctx.strokeRect(b[0]*zoom+.5,b[1]*zoom+.5,b[2]*zoom,b[3]*zoom); if(manual){{ctx.strokeStyle='#0a0';ctx.lineWidth=2;ctx.strokeRect(manual[0]*zoom+.5,manual[1]*zoom+.5,manual[2]*zoom,manual[3]*zoom);}}}}
function showCoords(){{if(!payload)return; const auto=[payload.origin[0]+payload.box[0],payload.origin[1]+payload.box[1],payload.box[2],payload.box[3]]; let s='auto column bbox: '+JSON.stringify(auto)+'\\npage bbox: '+JSON.stringify(payload.page_bbox); if(manual){{const m=[payload.origin[0]+manual[0],payload.origin[1]+manual[1],manual[2],manual[3]];s+='\\nmanual column bbox: '+JSON.stringify(m);}} coords.textContent=s;}}
document.querySelectorAll('.review').forEach(b=>b.addEventListener('click',()=>{{payload=JSON.parse(b.dataset.review);manual=null;title.textContent=payload.label+' · '+payload.style+' · sida '+payload.page+' spalt '+payload.column;facsimile.href=payload.source||'#';facsimile.style.display=payload.source?'inline-block':'none';img.onload=()=>{{img.style.width=(img.naturalWidth*zoom)+'px';img.style.height=(img.naturalHeight*zoom)+'px';canvas.width=img.naturalWidth*zoom;canvas.height=img.naturalHeight*zoom;canvas.style.width=canvas.width+'px';canvas.style.height=canvas.height+'px';draw();showCoords();}};img.src=payload.context;modal.classList.add('open');}}));
document.getElementById('close').onclick=()=>modal.classList.remove('open');modal.addEventListener('click',e=>{{if(e.target===modal)modal.classList.remove('open')}});
canvas.addEventListener('pointerdown',e=>{{dragging=true;const r=canvas.getBoundingClientRect();start=[(e.clientX-r.left)/zoom,(e.clientY-r.top)/zoom];manual=[start[0],start[1],0,0];canvas.setPointerCapture(e.pointerId);}});
canvas.addEventListener('pointermove',e=>{{if(!dragging)return;const r=canvas.getBoundingClientRect(),x=(e.clientX-r.left)/zoom,y=(e.clientY-r.top)/zoom;manual=[Math.min(start[0],x),Math.min(start[1],y),Math.abs(x-start[0]),Math.abs(y-start[1])].map(Math.round);draw();showCoords();}});
canvas.addEventListener('pointerup',()=>{{dragging=false;draw();showCoords();}});
document.getElementById('resetbox').onclick=()=>{{manual=null;draw();showCoords();}};
document.getElementById('copybox').onclick=async()=>{{if(!manual||!payload)return;const m=[payload.origin[0]+manual[0],payload.origin[1]+manual[1],manual[2],manual[3]];const out={{filename:payload.filename,page:payload.page,column:payload.column,bbox:m,label:payload.label,style:payload.style}};await navigator.clipboard.writeText(JSON.stringify(out));}};
</script>
'''
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(doc, encoding="utf-8")
    print(args.out)
    print(f"templates={total} styles={','.join(styles)} source_links={facsimile_links} source_contexts={source_contexts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
