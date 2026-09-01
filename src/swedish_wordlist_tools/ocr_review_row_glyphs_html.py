from __future__ import annotations

import argparse
import base64
import io
import json
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

from .ocr_add_row_residual_glyphs import add_or_merge_glyph, residual_component_pixels
from .ocr_column_row_segmentation import segment_page_rows
from .ocr_glyph_matcher import load_facit
from .ocr_prepare_sequential_page import _load_source_image, read_jsonl, source_for_page
from .ocr_probe_row_glyphs import analyse_row_exact, render_exact_markup, render_exact_text
from .ocr_row_map_words import _owned_row_crop, _persistent_left_rule_x, _row_crop_box


def normalize_points(points: set[tuple[int, int]], baseline: int) -> list[list[int]]:
    if not points:
        raise ValueError("cannot make a glyph from an empty selection")
    left = min(x for x, _y in points)
    return [[x - left, y - baseline] for x, y in sorted(points, key=lambda p: (p[0], p[1]))]


def glyph_from_points(label: str, style: str, points: set[tuple[int, int]], baseline: int, source: dict) -> dict:
    return {
        "label": label,
        "style": style,
        "pixels_relative_to_baseline": normalize_points(points, baseline),
        "sources": [source],
    }


def relabel_exact_model(payload: dict, *, old_label: str, old_style: str, pixels_relative_to_baseline: list[list[int]], new_label: str, new_style: str | None = None) -> int:
    target = tuple(tuple(point) for point in pixels_relative_to_baseline)
    found = []
    for glyph in payload.get("glyphs") or []:
        pixels = tuple(tuple(point) for point in glyph.get("pixels_relative_to_baseline") or [])
        if glyph.get("label") == old_label and glyph.get("style") == old_style and pixels == target:
            found.append(glyph)
    if len(found) != 1:
        raise ValueError(f"expected exactly one facit model for {old_label!r}/{old_style}, found {len(found)}")
    found[0]["label"] = new_label
    if new_style is not None:
        found[0]["style"] = new_style
    return 1


def _bbox(points: set[tuple[int, int]]) -> dict[str, int]:
    xs = [x for x, _y in points]
    ys = [y for _x, y in points]
    return {"left": min(xs), "top": min(ys), "right": max(xs) + 1, "bottom": max(ys) + 1}


def _png_data_uri(crop) -> str:
    buf = io.BytesIO()
    crop.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _trim_leading_white_columns(crop, *, threshold: int = 210, keep: int = 2):
    """Trim purely empty left margin while retaining a small visual cushion."""
    gray = crop.convert("L")
    pixels = gray.load()
    first_ink = next(
        (
            x
            for x in range(gray.width)
            if any(pixels[x, y] < threshold for y in range(gray.height))
        ),
        None,
    )
    if first_ink is None:
        return gray, 0
    trim = max(0, first_ink - max(0, int(keep)))
    if trim == 0:
        return gray, 0
    return gray.crop((trim, 0, gray.width, gray.height)), trim


def load_review_state(jsonl: Path, page_number: int, column: int, row_index: int, facit: Path, threshold: int = 210) -> dict:
    rows = list(read_jsonl(jsonl))
    source = source_for_page(rows, page_number)
    if not source:
        raise ValueError(f"no source found for page {page_number}")
    page = _load_source_image(source)
    if page is None:
        raise ValueError(f"could not load page image: {source}")
    row_map = segment_page_rows(page, threshold=threshold)
    column_entry = row_map["columns"][column]
    physical_rows = column_entry.get("rows") or []
    if not 0 <= row_index < len(physical_rows):
        raise ValueError(f"row {row_index} out of range; column {column} has {len(physical_rows)} rows")
    row = physical_rows[row_index]
    rule_x = _persistent_left_rule_x(page, column_entry, threshold=threshold)
    content_left = rule_x + 2 if rule_x is not None else None
    box = _row_crop_box(row, column=column, page_width=page.width, page_height=page.height, pad_y=1, left_override=content_left)
    crop, removed_neighbor_pixels = _owned_row_crop(page, row, box, threshold=threshold)
    crop, trimmed_left = _trim_leading_white_columns(crop, threshold=threshold, keep=2)
    if trimmed_left:
        box = (box[0] + trimmed_left, box[1], box[2], box[3])
    result = analyse_row_exact(crop, load_facit(facit), threshold=threshold)
    selected = result["selected"]
    covered = set().union(*(match.pixels for match in selected)) if selected else set()
    residual = result["ink"] - covered
    residuals = residual_component_pixels(residual)

    items = []
    point_sets: dict[str, frozenset[tuple[int, int]]] = {}
    for index, match in enumerate(selected):
        item_id = f"M{index:02d}"
        points = frozenset(match.pixels)
        point_sets[item_id] = points
        items.append({
            "id": item_id,
            "kind": "match",
            "label": match.label,
            "style": match.style,
            "pixels": len(points),
            "bbox": _bbox(set(points)),
        })
    for index, points in enumerate(residuals):
        item_id = f"U{index:02d}"
        point_sets[item_id] = points
        items.append({
            "id": item_id,
            "kind": "residual",
            "label": "?",
            "style": "unknown",
            "pixels": len(points),
            "bbox": _bbox(set(points)),
        })

    return {
        "source": source,
        "page": page_number,
        "column": column,
        "row": row_index,
        "row_page_top": int(row["page_top"]),
        "row_page_bottom": int(row["page_bottom"]),
        "crop_box": box,
        "crop_width": crop.width,
        "crop_height": crop.height,
        "image": _png_data_uri(crop),
        "baseline": result["baseline"],
        "covered_pixels": result["covered_pixels"],
        "source_pixels": result["source_pixels"],
        "source_ink_points": [[x, y] for x, y in sorted(result["ink"])],
        "removed_neighbor_pixels": removed_neighbor_pixels,
        "fully_exact": result["fully_exact"],
        "text": render_exact_text(selected, source_ink=result["ink"]) if selected else "",
        "markup": render_exact_markup(selected, source_ink=result["ink"]) if selected else "",
        "items": items,
        "point_sets": point_sets,
        "matches": selected,
    }


def selected_points(state: dict, ids: list[str]) -> set[tuple[int, int]]:
    if not ids:
        raise ValueError("select at least one glyph box")
    unknown = [item_id for item_id in ids if item_id not in state["point_sets"]]
    if unknown:
        raise ValueError("unknown selections: " + ", ".join(unknown))
    return set().union(*(state["point_sets"][item_id] for item_id in ids))


def parse_pixel_selection(value: str, source_ink: set[tuple[int, int]]) -> set[tuple[int, int]]:
    points: set[tuple[int, int]] = set()
    for token in value.split(";"):
        token = token.strip()
        if not token:
            continue
        try:
            sx, sy = token.split(",", 1)
            point = (int(sx), int(sy))
        except (ValueError, TypeError) as exc:
            raise ValueError(f"ogiltig pixel {token!r}") from exc
        if point not in source_ink:
            raise ValueError(f"vald pixel {point} är inte svart källpixel")
        points.add(point)
    return points


def render_html(state: dict, message: str = "") -> str:
    public = {key: value for key, value in state.items() if key not in {"point_sets", "matches"}}
    data = json.dumps(public, ensure_ascii=False).replace("</", "<\\/")
    message_html = message.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f'''<!doctype html>
<html lang="sv"><head><meta charset="utf-8"><title>SAOL glyphgranskning</title>
<style>
body{{font:16px system-ui,sans-serif;margin:20px;background:#f7f7f7;color:#171717}} h1{{font-size:22px}}
.rowbox{{overflow:auto;background:white;border:1px solid #bbb;padding:36px 8px 8px;margin:12px 0}}
canvas{{image-rendering:pixelated;cursor:pointer}} .controls{{display:flex;gap:10px;align-items:end;flex-wrap:wrap}}
label{{display:flex;flex-direction:column;gap:4px}} label.inline{{flex-direction:row;align-items:center;gap:6px}}
input,select,button{{font:inherit;padding:6px}} input[type=checkbox]{{padding:0}} button{{cursor:pointer}}
.items{{display:flex;flex-wrap:wrap;gap:5px;margin:10px 0}} .chip{{border:2px solid #888;background:white;padding:5px 7px}}
.chip.roman{{border-color:#1f6f8b;color:#174f63}} .chip.italic{{border-color:#98620c;color:#744a08}} .chip.bold{{border-color:#9b1c31;color:#781526;font-weight:700}}
.chip.residual{{border-color:#c77b00;color:#8a5500}} .chip.selected{{background:#dcecff;box-shadow:0 0 0 2px #1769d2 inset}}
.style-marker{{display:inline-block;min-width:.7em;text-align:center}} .style-marker.roman{{font-style:normal;font-weight:400}} .style-marker.italic{{font-style:italic;font-weight:400}} .style-marker.bold{{font-style:normal;font-weight:700}}
code{{background:#eee;padding:2px 4px}} .msg{{font-weight:600;margin:8px 0}} .hint{{max-width:1000px}}
</style></head><body>
<h1>SAOL glyphgranskning – sida {state['page']}, kolumn {state['column']}, rad {state['row']}</h1>
<div>Exakt: <b>{state['covered_pixels']}/{state['source_pixels']}</b> pixlar. Grannrad bortfiltrerad: <b>{state.get('removed_neighbor_pixels', 0)}</b> pixlar. Text: <code>{state['text']}</code></div>
<div class="msg">{message_html}</div>
<div class="controls">
<label class="inline"><input type="checkbox" id="showGrid" checked> Rutnät</label>
<label class="inline"><input type="checkbox" id="showBaseline" checked> Stödlinje</label>
<label class="inline"><input type="checkbox" id="pixelMode"> Pixel-läge</label>
<button type="button" id="clearPixels">Rensa pixelval</button>
<span id="pixelCount">0 valda pixlar</span>
</div>
<div class="rowbox"><canvas id="row"></canvas></div>
<div class="items" id="items"></div>
<form method="post" id="form">
<input type="hidden" name="selected" id="selected">
<input type="hidden" name="selected_pixels" id="selectedPixels">
<div class="controls">
<label>Glyph<input name="label" id="label" size="5" required></label>
<label>Stil<select name="style"><option>roman</option><option>italic</option><option>bold</option></select></label>
<button name="action" value="add">Lägg till/slå ihop valda pixlar som glyph</button>
<button name="action" value="relabel" type="submit">Rätta vald glyphs facitmodell</button>
</div></form>
<p class="hint">Normalläge: klicka glyphboxar eller omatchade boxar. <b>Pixel-läge:</b> dra en rektangel över svarta pixlar för att välja bara en del av en sammanhängande komponent; klicka en enskild svart pixel för att växla just den. Håll <b>Alt</b> medan du drar för att ta bort pixlar ur valet. Därmed kan exempelvis ett ihoptryckt <b>t;</b> delas i två separata glyphar trots att trycksvärtan går ihop med pixels bredsida.</p>
<script>
const S={data}; const scale=7, topPad=34; const canvas=document.getElementById('row'), ctx=canvas.getContext('2d');
const chosen=new Set(), chosenPixels=new Set(), sourceInk=new Set(S.source_ink_points.map(p=>p[0]+','+p[1])); const img=new Image(); img.src=S.image;
const showGrid=document.getElementById('showGrid'), showBaseline=document.getElementById('showBaseline'), pixelMode=document.getElementById('pixelMode');
let dragStart=null, dragNow=null, dragRemove=false;
function styleColor(it){{
 if(it.kind!=='match') return '#c77b00';
 if(it.style==='bold') return '#9b1c31';
 if(it.style==='italic') return '#98620c';
 return '#1f6f8b';
}}
function styleLetter(style){{return style==='bold'?'b':style==='italic'?'i':'r';}}
function drawGrid(){{
 if(!showGrid.checked) return;
 ctx.save(); ctx.strokeStyle='rgba(70,70,70,.22)'; ctx.lineWidth=1;
 for(let x=0;x<=S.crop_width;x++){{const xx=x*scale+.5;ctx.beginPath();ctx.moveTo(xx,topPad);ctx.lineTo(xx,topPad+S.crop_height*scale);ctx.stroke();}}
 for(let y=0;y<=S.crop_height;y++){{const yy=topPad+y*scale+.5;ctx.beginPath();ctx.moveTo(0,yy);ctx.lineTo(S.crop_width*scale,yy);ctx.stroke();}}
 ctx.restore();
}}
function drawBaseline(){{
 if(!showBaseline.checked || S.baseline===null) return;
 const y=topPad+(S.baseline+1)*scale+.5;
 ctx.save();ctx.strokeStyle='rgba(0,90,210,.95)';ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(S.crop_width*scale,y);ctx.stroke();
 ctx.fillStyle='rgba(0,90,210,.95)';ctx.font='12px monospace';ctx.textBaseline='bottom';ctx.fillText('baseline '+S.baseline,4,y-3);ctx.restore();
}}
function draw(){{
 canvas.width=S.crop_width*scale; canvas.height=S.crop_height*scale+topPad;
 ctx.imageSmoothingEnabled=false; ctx.fillStyle='white'; ctx.fillRect(0,0,canvas.width,canvas.height);
 ctx.drawImage(img,0,topPad,S.crop_width*scale,S.crop_height*scale);
 for(const key of chosenPixels){{const [x,y]=key.split(',').map(Number);ctx.fillStyle='rgba(0,150,210,.45)';ctx.fillRect(x*scale,topPad+y*scale,scale,scale);}}
 drawGrid(); drawBaseline();
 ctx.font='12px monospace'; ctx.textBaseline='bottom';
 for(const it of S.items){{const b=it.bbox,x=b.left*scale,y=topPad+b.top*scale,w=(b.right-b.left)*scale,h=(b.bottom-b.top)*scale;
   const on=chosen.has(it.id), color=styleColor(it); ctx.strokeStyle=on?'#1769d2':color;ctx.lineWidth=on?3:2;ctx.strokeRect(x,y,w,h);
   ctx.fillStyle=on?'#1769d2':color;ctx.fillText(it.kind==='match'?it.label:'?',x,topPad-3);
 }}
 if(dragStart&&dragNow){{const x=Math.min(dragStart.x,dragNow.x)*scale,y=topPad+Math.min(dragStart.y,dragNow.y)*scale,w=(Math.abs(dragStart.x-dragNow.x)+1)*scale,h=(Math.abs(dragStart.y-dragNow.y)+1)*scale;ctx.strokeStyle=dragRemove?'#b22':'#1769d2';ctx.lineWidth=2;ctx.strokeRect(x,y,w,h);}}
}}
function sync(){{
 document.getElementById('selected').value=[...chosen].join(',');
 document.getElementById('selectedPixels').value=[...chosenPixels].join(';');
 document.getElementById('pixelCount').textContent=chosenPixels.size+' valda pixlar';
 document.querySelectorAll('.chip').forEach(b=>b.classList.toggle('selected',chosen.has(b.dataset.id)));draw();
}}
function toggle(id){{chosen.has(id)?chosen.delete(id):chosen.add(id);sync();}}
function canvasPixel(e){{const r=canvas.getBoundingClientRect();return {{x:Math.max(0,Math.min(S.crop_width-1,Math.floor((e.clientX-r.left)*(canvas.width/r.width)/scale))),y:Math.max(0,Math.min(S.crop_height-1,Math.floor(((e.clientY-r.top)*(canvas.height/r.height)-topPad)/scale)))}};}}
for(const it of S.items){{
 const b=document.createElement('button'); b.type='button'; b.dataset.id=it.id; b.className='chip '+it.kind+' '+it.style;
 if(it.kind==='match'){{
   b.appendChild(document.createTextNode(JSON.stringify(it.label)+' · '));
   const marker=document.createElement('span'); marker.className='style-marker '+it.style; marker.textContent=styleLetter(it.style); b.appendChild(marker);
   b.appendChild(document.createTextNode(' · '+it.pixels+' px'));
 }} else {{b.textContent='omatchad · '+it.pixels+' px';}}
 b.onclick=()=>toggle(it.id); document.getElementById('items').appendChild(b);
}}
canvas.addEventListener('mousedown',e=>{{if(!pixelMode.checked)return;dragStart=canvasPixel(e);dragNow=dragStart;dragRemove=e.altKey;e.preventDefault();draw();}});
canvas.addEventListener('mousemove',e=>{{if(!dragStart)return;dragNow=canvasPixel(e);draw();}});
window.addEventListener('mouseup',e=>{{if(!dragStart)return;dragNow=canvasPixel(e);const x0=Math.min(dragStart.x,dragNow.x),x1=Math.max(dragStart.x,dragNow.x),y0=Math.min(dragStart.y,dragNow.y),y1=Math.max(dragStart.y,dragNow.y);for(let y=y0;y<=y1;y++)for(let x=x0;x<=x1;x++){{const key=x+','+y;if(sourceInk.has(key)){{if(dragRemove)chosenPixels.delete(key);else if(x0===x1&&y0===y1&&chosenPixels.has(key))chosenPixels.delete(key);else chosenPixels.add(key);}}}}dragStart=null;dragNow=null;sync();}});
canvas.addEventListener('click',e=>{{if(pixelMode.checked)return;const p=canvasPixel(e);const hits=S.items.filter(it=>p.x>=it.bbox.left&&p.x<it.bbox.right&&p.y>=it.bbox.top&&p.y<it.bbox.bottom);if(hits.length)toggle(hits[hits.length-1].id);}});
document.getElementById('clearPixels').onclick=()=>{{chosenPixels.clear();sync();}};
showGrid.addEventListener('change',draw); showBaseline.addEventListener('change',draw); pixelMode.addEventListener('change',draw); img.onload=draw;
</script></body></html>'''


def apply_edit(state: dict, facit: Path, form: dict[str, list[str]]) -> str:
    action = (form.get("action") or [""])[0]
    label = (form.get("label") or [""])[0]
    style = (form.get("style") or ["roman"])[0]
    ids = [item for item in (form.get("selected") or [""])[0].split(",") if item]
    pixel_value = (form.get("selected_pixels") or [""])[0]
    if not label:
        raise ValueError("glyph label may not be empty")
    if state["baseline"] is None:
        raise ValueError("row has no support baseline")
    payload = json.loads(facit.read_text(encoding="utf-8"))
    source_ink = {tuple(point) for point in state.get("source_ink_points") or []}
    pixel_points = parse_pixel_selection(pixel_value, source_ink) if pixel_value.strip() else set()
    source = {
        "page": state["page"],
        "column": state["column"],
        "row": state["row"],
        "review_selection": ids,
        "review_pixel_count": len(pixel_points),
        "source": state["source"],
    }
    if action == "add":
        points = pixel_points if pixel_points else selected_points(state, ids)
        glyph = glyph_from_points(label, style, points, int(state["baseline"]), source)
        outcome = add_or_merge_glyph(payload, glyph)
        facit.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        origin = f"{len(pixel_points)} handvalda pixlar" if pixel_points else ",".join(ids)
        return f"{outcome}: {label!r}/{style} från {origin}"
    if action == "relabel":
        if pixel_points:
            raise ValueError("Rätta facitmodell använder vald glyph, inte handvalda pixlar")
        if len(ids) != 1 or not ids[0].startswith("M"):
            raise ValueError("Rätta kräver exakt en vald matchad glyph")
        index = int(ids[0][1:])
        match = state["matches"][index]
        pixels = normalize_points(set(match.pixels), int(match.baseline))
        relabel_exact_model(payload, old_label=match.label, old_style=match.style, pixels_relative_to_baseline=pixels, new_label=label, new_style=style)
        facit.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return f"rättad: {match.label!r}/{match.style} → {label!r}/{style}"
    raise ValueError(f"unknown action: {action!r}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Open a local HTML editor for one exact SAOL row and its residual glyphs.")
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--page", type=int, required=True)
    ap.add_argument("--column", type=int, choices=(0, 1, 2), required=True)
    ap.add_argument("--row", type=int, required=True)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--facit", type=Path, default=Path("glyphs/saol14-manual-glyph-facit.json"))
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()
    message = {"text": ""}

    class Handler(BaseHTTPRequestHandler):
        def _state(self):
            return load_review_state(args.jsonl, args.page, args.column, args.row, args.facit, args.threshold)

        def do_GET(self):
            if self.path != "/":
                self.send_error(404); return
            try:
                html = render_html(self._state(), message["text"]).encode("utf-8")
                message["text"] = ""
                self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Content-Length", str(len(html))); self.end_headers(); self.wfile.write(html)
            except Exception as exc:
                self.send_error(500, str(exc))

        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            form = parse_qs(self.rfile.read(length).decode("utf-8"), keep_blank_values=True)
            try:
                message["text"] = apply_edit(self._state(), args.facit, form)
            except Exception as exc:
                message["text"] = "FEL: " + str(exc)
            self.send_response(303); self.send_header("Location", "/"); self.end_headers()

        def log_message(self, fmt, *values):
            print("review:", fmt % values)

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}/"
    print(url)
    print(f"facit={args.facit} (ändringar sparas direkt lokalt; Ctrl-C avslutar)")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
