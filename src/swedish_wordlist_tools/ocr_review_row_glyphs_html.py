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
from .ocr_row_map_words import _persistent_left_rule_x, _row_crop_box


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
    crop = page.crop(box).convert("L")
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
        "fully_exact": result["fully_exact"],
        "text": render_exact_text(selected, source_ink=result["ink"]) if selected else "",
        "markup": render_exact_markup(selected, source_ink=result["ink"]) if selected else "",
        "items": items,
        "point_sets": point_sets,
        "matches": selected,
    }


def selected_points(state: dict, ids: list[str]) -> set[tuple[int, int]]:
    if not ids:
        raise ValueError("select at least one M/U box")
    unknown = [item_id for item_id in ids if item_id not in state["point_sets"]]
    if unknown:
        raise ValueError("unknown selections: " + ", ".join(unknown))
    return set().union(*(state["point_sets"][item_id] for item_id in ids))


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
.chip.match{{border-color:#b22}} .chip.residual{{border-color:#c77b00}} .chip.selected{{background:#dcecff}}
code{{background:#eee;padding:2px 4px}} .msg{{font-weight:600;margin:8px 0}} .hint{{max-width:1000px}}
</style></head><body>
<h1>SAOL glyphgranskning – sida {state['page']}, kolumn {state['column']}, rad {state['row']}</h1>
<div>Exakt: <b>{state['covered_pixels']}/{state['source_pixels']}</b> pixlar. Text: <code>{state['text']}</code></div>
<div class="msg">{message_html}</div>
<div class="controls">
<label class="inline"><input type="checkbox" id="showGrid" checked> Rutnät</label>
<label class="inline"><input type="checkbox" id="showBaseline" checked> Stödlinje</label>
</div>
<div class="rowbox"><canvas id="row"></canvas></div>
<div class="items" id="items"></div>
<form method="post" id="form">
<input type="hidden" name="selected" id="selected">
<div class="controls">
<label>Glyph<input name="label" id="label" size="5" required></label>
<label>Stil<select name="style"><option>roman</option><option>italic</option><option>bold</option></select></label>
<button name="action" value="add">Lägg till/slå ihop valda pixlar som glyph</button>
<button name="action" value="relabel" type="submit">Rätta vald M-glyphs facitmodell</button>
</div></form>
<p class="hint">Ändringar sparas direkt i facitfilen när du trycker på en åtgärdsknapp. Klicka på boxar i bilden eller knapparna nedanför. Röda <b>Mxx</b> är nuvarande exakta facitmatchningar; orange <b>Uxx</b> är omatchat bläck. För exempelvis <b>å</b>: välj både M-boxen för a-kroppen och U-boxen för ringen, skriv å och lägg till som en glyph.</p>
<script>
const S={data}; const scale=7, topPad=34; const canvas=document.getElementById('row'), ctx=canvas.getContext('2d');
const chosen=new Set(); const img=new Image(); img.src=S.image;
const showGrid=document.getElementById('showGrid'), showBaseline=document.getElementById('showBaseline');
function drawGrid(){{
 if(!showGrid.checked) return;
 ctx.save(); ctx.strokeStyle='rgba(70,70,70,.22)'; ctx.lineWidth=1;
 for(let x=0;x<=S.crop_width;x++){{const xx=x*scale+.5;ctx.beginPath();ctx.moveTo(xx,topPad);ctx.lineTo(xx,topPad+S.crop_height*scale);ctx.stroke();}}
 for(let y=0;y<=S.crop_height;y++){{const yy=topPad+y*scale+.5;ctx.beginPath();ctx.moveTo(0,yy);ctx.lineTo(S.crop_width*scale,yy);ctx.stroke();}}
 ctx.restore();
}}
function drawBaseline(){{
 if(!showBaseline.checked || S.baseline===null) return;
 // The matcher baseline is a source-pixel row. Draw the typographic support
 // line on the lower edge of that row, coincident with the pixel grid.
 const y=topPad+(S.baseline+1)*scale+.5;
 ctx.save();ctx.strokeStyle='rgba(0,90,210,.95)';ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(S.crop_width*scale,y);ctx.stroke();
 ctx.fillStyle='rgba(0,90,210,.95)';ctx.font='12px monospace';ctx.textBaseline='bottom';ctx.fillText('baseline '+S.baseline,4,y-3);ctx.restore();
}}
function draw(){{
 canvas.width=S.crop_width*scale; canvas.height=S.crop_height*scale+topPad;
 ctx.imageSmoothingEnabled=false; ctx.fillStyle='white'; ctx.fillRect(0,0,canvas.width,canvas.height);
 ctx.drawImage(img,0,topPad,S.crop_width*scale,S.crop_height*scale);
 drawGrid(); drawBaseline();
 ctx.font='12px monospace'; ctx.textBaseline='bottom';
 for(const it of S.items){{const b=it.bbox,x=b.left*scale,y=topPad+b.top*scale,w=(b.right-b.left)*scale,h=(b.bottom-b.top)*scale;
   const on=chosen.has(it.id); ctx.strokeStyle=on?'#1769d2':(it.kind==='match'?'#b22':'#c77b00');ctx.lineWidth=on?3:2;ctx.strokeRect(x,y,w,h);
   ctx.fillStyle=ctx.strokeStyle;ctx.fillText(it.id+' '+it.label,x,topPad-3);
 }}
}}
function sync(){{document.getElementById('selected').value=[...chosen].join(',');document.querySelectorAll('.chip').forEach(b=>b.classList.toggle('selected',chosen.has(b.dataset.id)));draw();}}
function toggle(id){{chosen.has(id)?chosen.delete(id):chosen.add(id);sync();}}
for(const it of S.items){{const b=document.createElement('button');b.type='button';b.dataset.id=it.id;b.className='chip '+it.kind;b.textContent=it.id+' '+(it.kind==='match'?JSON.stringify(it.label):'omatchad')+' · '+it.style+' · '+it.pixels+' px';b.onclick=()=>toggle(it.id);document.getElementById('items').appendChild(b);}}
canvas.addEventListener('click',e=>{{const r=canvas.getBoundingClientRect(),px=(e.clientX-r.left)*(canvas.width/r.width)/scale,py=((e.clientY-r.top)*(canvas.height/r.height)-topPad)/scale;const hits=S.items.filter(it=>px>=it.bbox.left&&px<it.bbox.right&&py>=it.bbox.top&&py<it.bbox.bottom);if(hits.length)toggle(hits[hits.length-1].id);}});
showGrid.addEventListener('change',draw); showBaseline.addEventListener('change',draw); img.onload=draw;
</script></body></html>'''


def apply_edit(state: dict, facit: Path, form: dict[str, list[str]]) -> str:
    action = (form.get("action") or [""])[0]
    label = (form.get("label") or [""])[0]
    style = (form.get("style") or ["roman"])[0]
    ids = [item for item in (form.get("selected") or [""])[0].split(",") if item]
    if not label:
        raise ValueError("glyph label may not be empty")
    if state["baseline"] is None:
        raise ValueError("row has no support baseline")
    payload = json.loads(facit.read_text(encoding="utf-8"))
    source = {"page": state["page"], "column": state["column"], "row": state["row"], "review_selection": ids, "source": state["source"]}
    if action == "add":
        points = selected_points(state, ids)
        glyph = glyph_from_points(label, style, points, int(state["baseline"]), source)
        outcome = add_or_merge_glyph(payload, glyph)
        facit.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return f"{outcome}: {label!r}/{style} från {','.join(ids)}"
    if action == "relabel":
        if len(ids) != 1 or not ids[0].startswith("M"):
            raise ValueError("Rätta kräver exakt en vald M-glyph")
        index = int(ids[0][1:])
        match = state["matches"][index]
        pixels = normalize_points(set(match.pixels), int(match.baseline))
        relabel_exact_model(payload, old_label=match.label, old_style=match.style, pixels_relative_to_baseline=pixels, new_label=label, new_style=style)
        facit.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return f"rättad: {ids[0]} {match.label!r}/{match.style} → {label!r}/{style}"
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
