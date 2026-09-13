from __future__ import annotations

import argparse
import base64
import html
import io
import json
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

from PIL import Image

from . import ocr_profile_automaton_batch as batch
from .ocr_glyph_facit_store import (
    canonical_store_for_facit,
    load_split_facit,
    persist_facit_payload,
)
from .ocr_profile_automaton_parallel_benchmark import (
    _build_minimal_page_context,
    _minimal_column_bounds,
)


STYLES = ("roman", "italic", "bold")


def _png_data_uri(image: Image.Image) -> str:
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _parse_points(value: str) -> set[tuple[int, int]]:
    points: set[tuple[int, int]] = set()
    for token in value.split(";"):
        token = token.strip()
        if not token:
            continue
        sx, sy = token.split(",", 1)
        points.add((int(sx), int(sy)))
    return points


def _merge_glyph(payload: dict, glyph: dict) -> str:
    key = (
        glyph["label"],
        glyph["style"],
        tuple(tuple(p) for p in glyph["pixels_relative_to_baseline"]),
    )
    for existing in payload.get("glyphs") or []:
        existing_key = (
            str(existing.get("label") or ""),
            str(existing.get("style") or "roman"),
            tuple(tuple(p) for p in existing.get("pixels_relative_to_baseline") or []),
        )
        if existing_key != key:
            continue
        known = {
            json.dumps(source, ensure_ascii=False, sort_keys=True)
            for source in existing.get("sources") or []
        }
        for source in glyph.get("sources") or []:
            encoded = json.dumps(source, ensure_ascii=False, sort_keys=True)
            if encoded not in known:
                existing.setdefault("sources", []).append(source)
        existing["reviewed"] = True
        return "merged"
    payload.setdefault("glyphs", []).append(glyph)
    return "added"


class ProfilePageEditor:
    def __init__(
        self,
        *,
        jsonl: Path,
        facit: Path,
        page: int,
        threshold: int,
        prefix_len: int,
        frontier_slack: int,
    ):
        self.jsonl = jsonl
        self.facit = facit
        self.page_number = int(page)
        self.threshold = int(threshold)
        self.prefix_len = int(prefix_len)
        self.frontier_slack = int(frontier_slack)
        self.message = ""
        self.context: dict | None = None
        self.result: dict | None = None
        self.recompute("initial")

    def recompute(self, reason: str) -> None:
        print(f"profile-editor: räknar om hela sida {self.page_number} ({reason}) ...", flush=True)
        batch._init_worker(
            str(self.jsonl),
            str(self.facit),
            self.threshold,
            self.prefix_len,
            "",
            "",
        )
        self.context = _build_minimal_page_context(
            self.jsonl,
            self.page_number,
            self.threshold,
        )
        self.result = batch._ocr_page(self.page_number, self.frontier_slack)
        print(
            f"profile-editor: sida {self.page_number} klar: "
            f"rows={self.result['row_count']} active_remaining={self.result['active_remaining']} "
            f"deferred={self.result['deferred_remaining']}",
            flush=True,
        )

    def rows_flat(self) -> list[tuple[int, dict]]:
        assert self.result is not None
        out: list[tuple[int, dict]] = []
        for column in self.result["columns"]:
            c = int(column["column"])
            for row in column["rows"]:
                out.append((c, row))
        return out

    def locate(self, column: int, baseline: int | None) -> tuple[int, dict]:
        rows = self.rows_flat()
        same = [(c, row) for c, row in rows if c == int(column)]
        if not same:
            raise ValueError(f"kolumn {column} har inga rekonstruerade rader")
        if baseline is None:
            return same[0]
        return min(
            same,
            key=lambda pair: (
                abs(int(pair[1]["baseline"]) - int(baseline)),
                int(pair[1]["baseline"]),
            ),
        )

    def nav(self, current: tuple[int, dict], delta: int) -> tuple[int, dict] | None:
        rows = self.rows_flat()
        current_key = (current[0], int(current[1]["baseline"]))
        keys = [(c, int(row["baseline"])) for c, row in rows]
        try:
            index = keys.index(current_key)
        except ValueError:
            return None
        target = index + delta
        return rows[target] if 0 <= target < len(rows) else None

    def row_is_incomplete(self, pair: tuple[int, dict]) -> bool:
        assert self.result is not None
        column, row = pair
        top = int(row["page_top"])
        bottom = int(row["page_bottom"])
        deferred = {
            tuple(point)
            for point in self.result["columns"][column].get("deferred_pixels", [])
        }
        return any(top <= y < bottom for _x, y in deferred)

    def incomplete_nav(self, current: tuple[int, dict], delta: int) -> tuple[int, dict] | None:
        rows = self.rows_flat()
        keys = [(c, int(row["baseline"])) for c, row in rows]
        current_key = (current[0], int(current[1]["baseline"]))
        try:
            index = keys.index(current_key)
        except ValueError:
            return None
        step = 1 if delta >= 0 else -1
        for i in range(index + step, len(rows) if step > 0 else -1, step):
            if self.row_is_incomplete(rows[i]):
                return rows[i]
        return None

    def row_preview(self, pair: tuple[int, dict]) -> dict:
        assert self.context is not None and self.result is not None
        column, row = pair
        row_top = int(row["page_top"])
        row_bottom = int(row["page_bottom"])
        left, right, _ct, _cb = _minimal_column_bounds(self.context, column)
        top = max(0, row_top - 2)
        bottom = min(self.context["gray"].height, row_bottom + 2)
        gray = self.context["gray"]
        src = gray.load()
        raster = Image.new("L", (right - left, bottom - top), 255)
        rp = raster.load()
        for y in range(top, bottom):
            for x in range(left, right):
                if int(src[x, y]) < self.threshold:
                    rp[x - left, y - top] = 0
        return {
            "column": column,
            "baseline": int(row["baseline"]),
            "text": str(row.get("text") or ""),
            "image": _png_data_uri(raster),
            "incomplete": self.row_is_incomplete(pair),
            "url": "/?" + urlencode({"column": column, "baseline": int(row["baseline"])}),
        }

    def row_state(self, column: int, baseline: int | None) -> dict:
        assert self.context is not None and self.result is not None
        column, row = self.locate(column, baseline)
        row_top = int(row["page_top"])
        row_bottom = int(row["page_bottom"])
        col_left, col_right, col_top, col_bottom = _minimal_column_bounds(
            self.context, column
        )

        same_column_rows = sorted(
            [candidate for c, candidate in self.rows_flat() if c == column],
            key=lambda candidate: int(candidate["baseline"]),
        )
        current_pos = next(
            i for i, candidate in enumerate(same_column_rows)
            if int(candidate["baseline"]) == int(row["baseline"])
        )
        previous_row = same_column_rows[current_pos - 1] if current_pos > 0 else None
        next_row = same_column_rows[current_pos + 1] if current_pos + 1 < len(same_column_rows) else None
        baseline_page = int(row["baseline"])
        ownership_top = (
            (int(previous_row["baseline"]) + baseline_page) // 2 + 1
            if previous_row is not None else col_top
        )
        ownership_bottom = (
            (baseline_page + int(next_row["baseline"])) // 2 + 1
            if next_row is not None else col_bottom
        )

        match_tops = [int(match["top"]) for match in row.get("matches") or []]
        match_bottoms = [int(match["bottom"]) for match in row.get("matches") or []]
        top = max(col_top, min(match_tops) if match_tops else row_top)
        bottom = min(col_bottom, max(match_bottoms) if match_bottoms else row_bottom)
        left = col_left
        right = col_right
        gray = self.context["gray"]
        pixels = gray.load()

        # source_points is filled after excluding pixels already explained
        # by matched glyphs on neighbouring reconstructed rows.
        source_points = []

        other_owned_points: set[tuple[int, int]] = set()
        for other in same_column_rows:
            if int(other["baseline"]) == baseline_page:
                continue
            for match in other.get("matches") or []:
                other_owned_points.update(
                    (int(x), int(y))
                    for x, y in match.get("points") or []
                )

        row_source_page_points = {
            (x, y)
            for y in range(top, bottom)
            for x in range(left, right)
            if int(pixels[x, y]) < self.threshold
            and (x, y) not in other_owned_points
        }
        row_source_pixels = len(row_source_page_points)
        source_points = [
            [x - left, y - top]
            for x, y in sorted(row_source_page_points, key=lambda p: (p[1], p[0]))
        ]
        row_matches = []
        matched_page_points: set[tuple[int, int]] = set()
        for match in row.get("matches") or []:
            owned_points = {
                (int(x), int(y))
                for x, y in match.get("points") or []
                if left <= int(x) < right
                and top <= int(y) < bottom
            }
            if not owned_points:
                continue
            matched_page_points.update(owned_points)
            match_left = min(x for x, _y in owned_points)
            match_right = max(x for x, _y in owned_points) + 1
            row_matches.append({
                "left": match_left - left,
                "right": match_right - left,
                "label": str(match["label"]),
                "style": str(match.get("style") or "roman"),
                "width": match_right - match_left,
                "pixels": len(owned_points),
            })
        matched_pixels = len(matched_page_points)

        column_result = self.result["columns"][column]
        deferred_page = {
            tuple(point) for point in column_result.get("deferred_pixels", [])
        }
        deferred_local = [
            [x - left, y - top]
            for x, y in sorted(deferred_page)
            if left <= x < right and top <= y < bottom
        ]

        # Binary OCR image, exactly gray<threshold.
        raster = Image.new("L", (right - left, bottom - top), 255)
        rp = raster.load()
        for lx, ly in source_points:
            rp[lx, ly] = 0

        current = (column, row)
        previous = self.nav(current, -1)
        following = self.nav(current, +1)
        previous_incomplete = self.incomplete_nav(current, -1)
        next_incomplete = self.incomplete_nav(current, +1)
        context_pairs = [pair for pair in (previous, current, following) if pair is not None]

        def link_for(pair):
            if pair is None:
                return None
            c, r = pair
            return "/?" + urlencode({"column": c, "baseline": int(r["baseline"])})

        return {
            "page": self.page_number,
            "column": column,
            "row_index": int(row["index"]),
            "baseline_page": int(row["baseline"]),
            "baseline_local": int(row["baseline"]) - top,
            "row_page_top": row_top,
            "row_page_bottom": row_bottom,
            "crop_box": [left, top, right, bottom],
            "width": right - left,
            "height": bottom - top,
            "text": str(row.get("text") or ""),
            "glyphs": int(row.get("glyphs") or 0),
            "matched_pixels": matched_pixels,
            "source_pixels": row_source_pixels,
            "matches": row_matches,
            "source_points": source_points,
            "deferred_points": deferred_local,
            "image": _png_data_uri(raster),
            "previous_url": link_for(previous),
            "next_url": link_for(following),
            "previous_incomplete_url": link_for(previous_incomplete),
            "next_incomplete_url": link_for(next_incomplete),
            "context_rows": [self.row_preview(pair) for pair in context_pairs],
            "active_remaining": int(self.result["active_remaining"]),
            "deferred_remaining": int(self.result["deferred_remaining"]),
            "row_count": int(self.result["row_count"]),
            "dump_url": "/dump?" + urlencode({
                "column": column,
                "baseline": int(row["baseline"]),
            }),
        }

    def add_glyph(self, state: dict, form: dict[str, list[str]]) -> str:
        label = (form.get("label") or [""])[0]
        style = (form.get("style") or ["roman"])[0]
        if not label:
            raise ValueError("glyph måste ha ett namn")
        if style not in STYLES:
            raise ValueError(f"ogiltig stil: {style}")

        local_points = _parse_points((form.get("selected_pixels") or [""])[0])
        if not local_points:
            raise ValueError("markera minst en svart pixel")

        source = {tuple(point) for point in state["source_points"]}
        if not local_points <= source:
            raise ValueError("pixelvalet innehåller pixel som inte är svart i OCR-rastret")

        left, top, _right, _bottom = state["crop_box"]
        page_points = {(left + x, top + y) for x, y in local_points}
        glyph_left = min(x for x, _y in page_points)
        baseline = int(state["baseline_page"])
        normalized = sorted(
            (x - glyph_left, y - baseline)
            for x, y in page_points
        )

        store = canonical_store_for_facit(self.facit)
        if store is None:
            raise ValueError("editorn kräver canonical saol14-manual-glyph-facit-v2.json")
        payload = load_split_facit(store)
        glyph = {
            "label": label,
            "role": "unknown",
            "style": style,
            "pixels_relative_to_baseline": [[x, y] for x, y in normalized],
            "sources": [{
                "page": self.page_number,
                "column": int(state["column"]),
                "baseline": baseline,
                "page_bbox": [
                    min(x for x, _y in page_points),
                    min(y for _x, y in page_points),
                    max(x for x, _y in page_points) + 1,
                    max(y for _x, y in page_points) + 1,
                ],
                "source": "profile-page-editor",
            }],
            "reviewed": True,
        }
        outcome = _merge_glyph(payload, glyph)
        count, assigned = persist_facit_payload(self.facit, payload, store_dir=store)
        self.recompute(f"{outcome} {label!r}/{style}; facit={count}, nya id={assigned}")
        return f"{outcome}: {label!r}/{style} ({len(page_points)} px)"


def render_html(state: dict, message: str = "") -> str:
    data = json.dumps(state, ensure_ascii=False).replace("</", "<\\/")
    msg = html.escape(message)
    prev_link = (
        f'<a class="nav" href="{state["previous_url"]}">← föregående rad</a>'
        if state["previous_url"] else '<span class="nav disabled">← föregående rad</span>'
    )
    next_link = (
        f'<a class="nav" href="{state["next_url"]}">nästa rad →</a>'
        if state["next_url"] else '<span class="nav disabled">nästa rad →</span>'
    )
    prev_incomplete = (
        f'<a class="nav defect" href="{state["previous_incomplete_url"]}">← förra ickeklara</a>'
        if state["previous_incomplete_url"] else '<span class="nav disabled">← förra ickeklara</span>'
    )
    next_incomplete = (
        f'<a class="nav defect" href="{state["next_incomplete_url"]}">nästa ickeklara →</a>'
        if state["next_incomplete_url"] else '<span class="nav disabled">nästa ickeklara →</span>'
    )
    context_cards = "".join(
        '<a class="context-card' + (' active' if row["baseline"] == state["baseline_page"] and row["column"] == state["column"] else '') +
        (' incomplete' if row["incomplete"] else '') + '" href="' + row["url"] + '">' +
        f'<div>kol {row["column"]} · baseline {row["baseline"]}' + (' · ickeklar' if row["incomplete"] else '') + '</div>' +
        '<img src="' + row["image"] + '">' +
        '<div class="context-text">' + html.escape(row["text"]) + '</div></a>'
        for row in state["context_rows"]
    )
    return f"""<!doctype html>
<html lang="sv"><head><meta charset="utf-8">
<title>SAOL profil-OCR editor</title>
<style>
body{{font:16px system-ui,sans-serif;margin:18px;background:#f4f4f4;color:#171717}}
h1{{font-size:21px;margin:0 0 8px}} code{{background:#eee;padding:2px 4px}}
.navbar,.controls{{display:flex;gap:8px;align-items:end;flex-wrap:wrap;margin:10px 0}}
.nav{{padding:6px 10px;border:1px solid #888;background:white;color:#111;text-decoration:none;border-radius:4px}}
.disabled{{opacity:.35}} .rowbox{{overflow:auto;border:1px solid #aaa;background:white;padding:8px}}
.pixel-wrap{{display:inline-block;min-width:max-content}}
canvas{{display:block;image-rendering:pixelated;cursor:crosshair;touch-action:none}}
.matchband{{position:relative;height:68px;margin-top:2px;background:#fafafa;border-top:1px solid #bbb;font:12px/13px monospace}}
.match-label{{position:absolute;top:2px;text-align:center;overflow:visible;white-space:nowrap;border-left:1px solid rgba(0,0,0,.15);border-right:1px solid rgba(0,0,0,.15);box-sizing:border-box}}
.match-label .glyph{{font-size:16px;line-height:17px}}
.match-label.roman{{color:#0b57d0}}
.match-label.italic{{color:#188038}}
.match-label.bold{{color:#111}}
.match-label.italic .glyph{{font-style:italic}}
.match-label.bold .glyph{{font-weight:700}}
.coverage{{font-size:18px;font-weight:700;margin:8px 0 4px}}
label{{display:flex;flex-direction:column;gap:3px}} input,select,button{{font:inherit;padding:6px}}
.msg{{font-weight:700;margin:8px 0}} .stats{{margin:6px 0}}
.hint{{max-width:1100px}} .red{{color:#b00020;font-weight:700}}
.nav.defect{{border-color:#b00020;background:#fff3f5;font-weight:700}}
.context{{display:grid;grid-template-columns:repeat(3,minmax(220px,1fr));gap:8px;max-width:1250px;margin:10px 0 14px}}
.context-card{{display:block;border:2px solid #bbb;background:white;padding:6px;color:#171717;text-decoration:none;min-width:0}}
.context-card.active{{border:4px solid #1769d2;padding:4px;background:#eef6ff}}
.context-card.incomplete{{box-shadow:inset 0 0 0 2px #b00020}}
.context-card img{{width:100%;height:72px;object-fit:contain;object-position:left center;image-rendering:pixelated;background:white}}
.context-text{{font:12px monospace;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
@media(max-width:900px){{.context{{grid-template-columns:1fr}}}}
</style></head><body>
<h1>SAOL profil-OCR – sida {state['page']}, kolumn {state['column']}, baseline {state['baseline_page']}</h1>
<div class="navbar">{prev_link}{next_link}{prev_incomplete}{next_incomplete}
<a class="nav" href="/?column={state['column']}&baseline={state['baseline_page']}&refresh=1">↻ räkna om hela sidan</a>
<a class="nav" href="{state['dump_url']}">⬇ Dumpa raster</a>
</div>
<div class="context">{context_cards}</div>
<div class="stats">Rekonstruerad rad {state['row_index']}; y={state['row_page_top']}..{state['row_page_bottom']-1};
glyphar={state['glyphs']}; text=<code>{html.escape(state['text'])}</code>.
Sidan: {state['row_count']} rader, active_remaining={state['active_remaining']},
deferred=<span class="red">{state['deferred_remaining']}</span>.</div>
<div class="msg">{msg}</div>
<div class="controls">
<label class="inline"><input id="grid" type="checkbox" checked> rutnät</label>
<label class="inline"><input id="baseline" type="checkbox" checked> baseline</label>
<button type="button" id="clear">Rensa pixelval</button>
<span id="count">0 valda pixlar</span>
</div>
<div class="coverage">{state['matched_pixels']}/{state['source_pixels']} px matchade</div>
<div class="rowbox"><div class="pixel-wrap"><canvas id="row"></canvas><div id="matchband" class="matchband"></div></div></div>
<form method="post">
<input type="hidden" name="selected_pixels" id="selectedPixels">
<input type="hidden" name="column" value="{state['column']}">
<input type="hidden" name="baseline" value="{state['baseline_page']}">
<div class="controls">
<label>Glyph<input name="label" size="7" required autofocus></label>
<label>Stil<select name="style"><option>roman</option><option>italic</option><option>bold</option></select></label>
<button type="submit">Spara glyph och räkna om hela sidan</button>
</div>
</form>
<p class="hint">Dra en rektangel över svarta pixlar för att välja dem. Shift-klick lägger till en enskild svart pixel; Alt-klick tar bort. Röda rutor är deferred-pixlar från profil-OCR:n. De tre små raderna ovan visar föregående, aktuell och nästa rad. "Ickeklar" betyder att raden innehåller deferred-pixlar. Efter sparning byggs facit/trie om, hela sidan OCR:as om och editorn återgår till raden närmast samma baseline.</p>
<script>
const S={data}, scale=9, topPad=28;
const canvas=document.getElementById('row'),ctx=canvas.getContext('2d'),matchband=document.getElementById('matchband');
const source=new Set(S.source_points.map(p=>p[0]+','+p[1]));
const deferred=new Set(S.deferred_points.map(p=>p[0]+','+p[1]));
const chosen=new Set(); let dragStart=null,dragNow=null;
const img=new Image();img.src=S.image;
function point(e){{const r=canvas.getBoundingClientRect();return {{
 x:Math.max(0,Math.min(S.width-1,Math.floor((e.clientX-r.left)*(canvas.width/r.width)/scale))),
 y:Math.max(0,Math.min(S.height-1,Math.floor(((e.clientY-r.top)*(canvas.height/r.height)-topPad)/scale)))
}};}}
function sync(){{document.getElementById('selectedPixels').value=[...chosen].join(';');document.getElementById('count').textContent=chosen.size+' valda pixlar';draw();}}
function renderMatchBand(){{
 matchband.style.width=(S.width*scale)+'px';
 matchband.innerHTML='';
 for(const m of S.matches){{
   const el=document.createElement('div');
   el.className='match-label '+m.style;
   el.style.left=(m.left*scale)+'px';
   el.style.width=Math.max((m.right-m.left)*scale,18)+'px';
   const styleLetter=m.style==='italic'?'i':m.style==='bold'?'b':'r';
   const glyph=document.createElement('div');glyph.className='glyph';glyph.textContent=m.label;
   const style=document.createElement('div');style.textContent=styleLetter;
   const width=document.createElement('div');width.textContent=String(m.width);
   const px=document.createElement('div');px.textContent='px';
   el.title=m.label+' / '+m.style+' / '+m.pixels+' matchade pixlar';
   el.append(glyph,style,width,px);
   matchband.appendChild(el);
 }}
}}
function draw(){{
 canvas.width=S.width*scale;canvas.height=S.height*scale+topPad;ctx.imageSmoothingEnabled=false;
 ctx.fillStyle='white';ctx.fillRect(0,0,canvas.width,canvas.height);
 ctx.drawImage(img,0,topPad,S.width*scale,S.height*scale);
 for(const key of deferred){{const [x,y]=key.split(',').map(Number);ctx.fillStyle='rgba(255,0,0,.60)';ctx.fillRect(x*scale,topPad+y*scale,scale,scale);}}
 for(const key of chosen){{const [x,y]=key.split(',').map(Number);ctx.fillStyle='rgba(0,145,230,.52)';ctx.fillRect(x*scale,topPad+y*scale,scale,scale);}}
 if(document.getElementById('grid').checked){{ctx.strokeStyle='rgba(80,80,80,.23)';ctx.lineWidth=1;
  for(let x=0;x<=S.width;x++){{let q=x*scale+.5;ctx.beginPath();ctx.moveTo(q,topPad);ctx.lineTo(q,topPad+S.height*scale);ctx.stroke();}}
  for(let y=0;y<=S.height;y++){{let q=topPad+y*scale+.5;ctx.beginPath();ctx.moveTo(0,q);ctx.lineTo(S.width*scale,q);ctx.stroke();}}
 }}
 if(document.getElementById('baseline').checked){{const y=topPad+(S.baseline_local+1)*scale+.5;ctx.strokeStyle='#0657c8';ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(S.width*scale,y);ctx.stroke();}}
 if(dragStart&&dragNow){{const x0=Math.min(dragStart.x,dragNow.x),x1=Math.max(dragStart.x,dragNow.x),y0=Math.min(dragStart.y,dragNow.y),y1=Math.max(dragStart.y,dragNow.y);ctx.strokeStyle='#0878cf';ctx.lineWidth=3;ctx.strokeRect(x0*scale,topPad+y0*scale,(x1-x0+1)*scale,(y1-y0+1)*scale);}}
 renderMatchBand();
}}
function chooseRect(a,b){{let x0=Math.min(a.x,b.x),x1=Math.max(a.x,b.x),y0=Math.min(a.y,b.y),y1=Math.max(a.y,b.y);for(let y=y0;y<=y1;y++)for(let x=x0;x<=x1;x++){{let k=x+','+y;if(source.has(k))chosen.add(k);}}}}
canvas.addEventListener('mousedown',e=>{{let p=point(e);if(e.shiftKey||e.altKey){{let k=p.x+','+p.y;if(source.has(k)){{if(e.altKey)chosen.delete(k);else chosen.add(k);sync();}}e.preventDefault();return;}}dragStart=p;dragNow=p;e.preventDefault();draw();}});
canvas.addEventListener('mousemove',e=>{{if(dragStart){{dragNow=point(e);draw();}}}});
window.addEventListener('mouseup',e=>{{if(!dragStart)return;dragNow=point(e);chooseRect(dragStart,dragNow);dragStart=null;dragNow=null;sync();}});
document.getElementById('clear').onclick=()=>{{chosen.clear();sync();}};
document.getElementById('grid').onchange=draw;document.getElementById('baseline').onchange=draw;
img.onload=draw;
document.addEventListener('keydown',e=>{{if(['INPUT','SELECT','TEXTAREA'].includes(e.target.tagName))return;if(e.key==='ArrowLeft'&&S.previous_url)location.href=S.previous_url;if(e.key==='ArrowRight'&&S.next_url)location.href=S.next_url;}});
</script>
</body></html>"""


def _render_dump_png(state: dict) -> bytes:
    from PIL import ImageDraw, ImageFont

    scale = 9
    top_pad = 34
    band_height = 72
    width = int(state["width"])
    height = int(state["height"])
    image = Image.new(
        "RGB",
        (width * scale, top_pad + height * scale + band_height),
        "white",
    )
    draw = ImageDraw.Draw(image)

    source = {tuple(point) for point in state["source_points"]}
    deferred = {tuple(point) for point in state["deferred_points"]}

    for y in range(height):
        for x in range(width):
            x0 = x * scale
            y0 = top_pad + y * scale
            fill = (0, 0, 0) if (x, y) in source else (255, 255, 255)
            if (x, y) in deferred:
                fill = (255, 0, 0)
            draw.rectangle((x0, y0, x0 + scale - 1, y0 + scale - 1), fill=fill)

    for x in range(width + 1):
        q = x * scale
        draw.line((q, top_pad, q, top_pad + height * scale), fill=(205, 205, 205), width=1)
    for y in range(height + 1):
        q = top_pad + y * scale
        draw.line((0, q, width * scale, q), fill=(205, 205, 205), width=1)

    baseline_y = top_pad + (int(state["baseline_local"]) + 1) * scale
    draw.line((0, baseline_y, width * scale, baseline_y), fill=(0, 90, 210), width=2)

    draw.text(
        (4, 4),
        f"{state['matched_pixels']}/{state['source_pixels']} px matchade  "
        f"page={state['page']} col={state['column']} baseline={state['baseline_page']}",
        fill=(0, 0, 0),
    )

    band_top = top_pad + height * scale + 2
    draw.line((0, band_top, width * scale, band_top), fill=(150, 150, 150), width=1)
    style_colors = {
        "roman": (11, 87, 208),
        "italic": (24, 128, 56),
        "bold": (17, 17, 17),
    }
    for match in state.get("matches") or []:
        x0 = int(match["left"]) * scale
        x1 = max(x0 + 18, int(match["right"]) * scale)
        colour = style_colors.get(str(match.get("style") or "roman"), (17, 17, 17))
        style_letter = {"roman": "r", "italic": "i", "bold": "b"}.get(
            str(match.get("style") or "roman"), "r"
        )
        label = str(match["label"])
        text = f"{label}\n{style_letter}\n{match['width']}\npx"
        draw.multiline_text((x0 + 2, band_top + 2), text, fill=colour, spacing=0)

    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def main() -> int:
    ap = argparse.ArgumentParser(description="Edit glyphs while rerunning whole-page profile OCR.")
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--facit", type=Path, required=True)
    ap.add_argument("--page", type=int, required=True)
    ap.add_argument("--column", type=int, default=0, choices=(0, 1, 2))
    ap.add_argument("--baseline", type=int)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--prefix-len", type=int, default=5)
    ap.add_argument("--frontier-slack", type=int, default=5)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    editor = ProfilePageEditor(
        jsonl=args.jsonl,
        facit=args.facit,
        page=args.page,
        threshold=args.threshold,
        prefix_len=args.prefix_len,
        frontier_slack=args.frontier_slack,
    )

    class Handler(BaseHTTPRequestHandler):
        def _params(self):
            return parse_qs(urlparse(self.path).query)

        def _target(self):
            query = self._params()
            column = int((query.get("column") or [str(args.column)])[0])
            raw = (query.get("baseline") or [str(args.baseline) if args.baseline is not None else ""])[0]
            baseline = int(raw) if raw else None
            if (query.get("refresh") or ["0"])[0] == "1":
                editor.recompute("manual refresh")
            return column, baseline

        def do_GET(self):
            path = urlparse(self.path).path
            if path not in {"/", "/dump"}:
                self.send_error(404)
                return
            try:
                column, baseline = self._target()
                state = editor.row_state(column, baseline)
                if path == "/dump":
                    body = _render_dump_png(state)
                    filename = (
                        f"saol14-page-{state['page']:04d}-col-{state['column']}-"
                        f"baseline-{state['baseline_page']}-raster.png"
                    )
                    self.send_response(200)
                    self.send_header("Content-Type", "image/png")
                    self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                body = render_html(state, editor.message).encode("utf-8")
                editor.message = ""
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception as exc:
                self.send_error(500, str(exc))

        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            form = parse_qs(
                self.rfile.read(length).decode("utf-8"),
                keep_blank_values=True,
            )
            try:
                column = int((form.get("column") or [str(args.column)])[0])
                baseline = int((form.get("baseline") or ["0"])[0])
                state = editor.row_state(column, baseline)
                editor.message = editor.add_glyph(state, form)
                target = editor.row_state(column, baseline)
                location = "/?" + urlencode({
                    "column": target["column"],
                    "baseline": target["baseline_page"],
                })
            except Exception as exc:
                editor.message = "FEL: " + str(exc)
                location = "/"
            self.send_response(303)
            self.send_header("Location", location)
            self.end_headers()

        def log_message(self, fmt, *values):
            print("profile-editor:", fmt % values)

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    initial = editor.row_state(args.column, args.baseline)
    url = f"http://{args.host}:{args.port}/?" + urlencode({
        "column": initial["column"],
        "baseline": initial["baseline_page"],
    })
    print(url)
    print(f"facit={args.facit} (sparas i canonical facit-v2; Ctrl-C avslutar)")
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
