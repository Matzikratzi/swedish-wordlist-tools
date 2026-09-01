from __future__ import annotations

import argparse
import json
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

from . import ocr_review_row_glyphs_html as legacy


def render_html(state: dict, message: str = "") -> str:
    public = {key: value for key, value in state.items() if key not in {"point_sets", "matches"}}
    data = json.dumps(public, ensure_ascii=False).replace("</", "<\\/")
    message_html = message.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f'''<!doctype html>
<html lang="sv"><head><meta charset="utf-8"><title>SAOL glyphgranskning – frihandsmask</title>
<style>
body{{font:16px system-ui,sans-serif;margin:20px;background:#f7f7f7;color:#171717}} h1{{font-size:22px}}
.rowbox{{overflow:auto;background:white;border:1px solid #bbb;padding:36px 8px 8px;margin:12px 0}}
canvas{{image-rendering:pixelated;cursor:crosshair;touch-action:none}} .controls{{display:flex;gap:10px;align-items:end;flex-wrap:wrap}}
label{{display:flex;flex-direction:column;gap:4px}} label.inline{{flex-direction:row;align-items:center;gap:6px}}
input,select,button{{font:inherit;padding:6px}} input[type=checkbox]{{padding:0}} button{{cursor:pointer}}
.items{{display:flex;flex-wrap:wrap;gap:4px;margin:10px 0;align-items:flex-start}} .chip{{border:2px solid #888;background:white;padding:4px 6px;min-width:38px;display:flex;flex-direction:column;align-items:center;justify-content:center;line-height:1.05;gap:2px}}
.chip.roman{{border-color:#1f6f8b;color:#174f63}} .chip.italic{{border-color:#98620c;color:#744a08}} .chip.bold{{border-color:#9b1c31;color:#781526;font-weight:700}}
.chip.residual{{border-color:#c77b00;color:#8a5500}} .chip.selected{{background:#dcecff;box-shadow:0 0 0 2px #1769d2 inset}}
.glyph-label{{white-space:nowrap}} .style-marker{{display:block;text-align:center}} .style-marker.roman{{font-style:normal;font-weight:400}} .style-marker.italic{{font-style:italic;font-weight:400}} .style-marker.bold{{font-style:normal;font-weight:700}} .pixel-count{{font-size:12px;font-weight:400;white-space:nowrap}}
code{{background:#eee;padding:2px 4px}} .msg{{font-weight:600;margin:8px 0}} .hint{{max-width:1100px}}
</style></head><body>
<h1>SAOL glyphgranskning – sida {state['page']}, kolumn {state['column']}, rad {state['row']}</h1>
<div>Exakt: <b>{state['covered_pixels']}/{state['source_pixels']}</b> pixlar. Grannrad bortfiltrerad: <b>{state.get('removed_neighbor_pixels', 0)}</b> pixlar. Text: <code>{state['text']}</code></div>
<div class="msg">{message_html}</div>
<div class="controls">
<label class="inline"><input type="checkbox" id="showGrid" checked> Rutnät</label>
<label class="inline"><input type="checkbox" id="showBaseline" checked> Stödlinje</label>
<label class="inline"><input type="checkbox" id="pixelMode" checked> Måla pixelmask</label>
<label>Pensel<select id="brushRadius"><option value="0">1 pixel</option><option value="1">3×3</option><option value="2">5×5</option></select></label>
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
<p class="hint"><b>Frihandsmask:</b> håll vänster musknapp och måla över glyphen. Endast svarta källpixlar kan väljas. Håll <b>Alt</b> medan du målar för att sudda. Den blå ramen är bara minsta omslutande box runt de faktiskt valda pixlarna; den avgör inte vilka pixlar som hör till glyphen. Därför får kursiva grannbokstävers ramar överlappa utan att deras pixlar blandas.</p>
<script>
const S={data};
const scale=7, topPad=34;
const canvas=document.getElementById('row'), ctx=canvas.getContext('2d');
const chosen=new Set(), chosenPixels=new Set();
const sourceInk=new Set(S.source_ink_points.map(p=>p[0]+','+p[1]));
const img=new Image(); img.src=S.image;
const showGrid=document.getElementById('showGrid');
const showBaseline=document.getElementById('showBaseline');
const pixelMode=document.getElementById('pixelMode');
const brushRadius=document.getElementById('brushRadius');
let painting=false, erase=false, lastPaint=null;

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
function selectedBounds(){{
 if(!chosenPixels.size) return null;
 let left=Infinity,top=Infinity,right=-Infinity,bottom=-Infinity;
 for(const key of chosenPixels){{const [x,y]=key.split(',').map(Number);left=Math.min(left,x);top=Math.min(top,y);right=Math.max(right,x);bottom=Math.max(bottom,y);}}
 return {{left,top,right:right+1,bottom:bottom+1}};
}}
function draw(){{
 canvas.width=S.crop_width*scale; canvas.height=S.crop_height*scale+topPad;
 ctx.imageSmoothingEnabled=false;ctx.fillStyle='white';ctx.fillRect(0,0,canvas.width,canvas.height);
 ctx.drawImage(img,0,topPad,S.crop_width*scale,S.crop_height*scale);
 for(const key of chosenPixels){{const [x,y]=key.split(',').map(Number);ctx.fillStyle='rgba(0,150,210,.48)';ctx.fillRect(x*scale,topPad+y*scale,scale,scale);}}
 drawGrid();drawBaseline();
 ctx.font='12px monospace';ctx.textBaseline='bottom';
 for(const it of S.items){{const b=it.bbox,x=b.left*scale,y=topPad+b.top*scale,w=(b.right-b.left)*scale,h=(b.bottom-b.top)*scale;const on=chosen.has(it.id),color=styleColor(it);ctx.strokeStyle=on?'#1769d2':color;ctx.lineWidth=on?3:2;ctx.strokeRect(x,y,w,h);ctx.fillStyle=on?'#1769d2':color;ctx.fillText(it.kind==='match'?it.label:'?',x,topPad-3);}}
 const b=selectedBounds();if(b){{ctx.save();ctx.strokeStyle='#1769d2';ctx.lineWidth=3;ctx.setLineDash([7,4]);ctx.strokeRect(b.left*scale,topPad+b.top*scale,(b.right-b.left)*scale,(b.bottom-b.top)*scale);ctx.restore();}}
}}
function sync(){{
 document.getElementById('selected').value=[...chosen].join(',');
 document.getElementById('selectedPixels').value=[...chosenPixels].join(';');
 document.getElementById('pixelCount').textContent=chosenPixels.size+' valda pixlar';
 document.querySelectorAll('.chip').forEach(b=>b.classList.toggle('selected',chosen.has(b.dataset.id)));draw();
}}
function toggle(id){{chosen.has(id)?chosen.delete(id):chosen.add(id);sync();}}
function canvasPixel(e){{
 const r=canvas.getBoundingClientRect();
 return {{x:Math.max(0,Math.min(S.crop_width-1,Math.floor((e.clientX-r.left)*(canvas.width/r.width)/scale))),y:Math.max(0,Math.min(S.crop_height-1,Math.floor(((e.clientY-r.top)*(canvas.height/r.height)-topPad)/scale)))}};
}}
function paintPoint(p, remove){{
 const radius=Number(brushRadius.value)||0;
 for(let dy=-radius;dy<=radius;dy++)for(let dx=-radius;dx<=radius;dx++){{const x=p.x+dx,y=p.y+dy;if(x<0||y<0||x>=S.crop_width||y>=S.crop_height)continue;const key=x+','+y;if(!sourceInk.has(key))continue;if(remove)chosenPixels.delete(key);else chosenPixels.add(key);}}
}}
function paintLine(a,b,remove){{
 let x0=a.x,y0=a.y,x1=b.x,y1=b.y;const dx=Math.abs(x1-x0),sx=x0<x1?1:-1,dy=-Math.abs(y1-y0),sy=y0<y1?1:-1;let err=dx+dy;
 while(true){{paintPoint({{x:x0,y:y0}},remove);if(x0===x1&&y0===y1)break;const e2=2*err;if(e2>=dy){{err+=dy;x0+=sx;}}if(e2<=dx){{err+=dx;y0+=sy;}}}}
}}

for(const it of S.items){{
 const b=document.createElement('button');b.type='button';b.dataset.id=it.id;b.className='chip '+it.kind+' '+it.style;
 if(it.kind==='match'){{const glyph=document.createElement('span');glyph.className='glyph-label';glyph.textContent=JSON.stringify(it.label);b.appendChild(glyph);const marker=document.createElement('span');marker.className='style-marker '+it.style;marker.textContent=styleLetter(it.style);b.appendChild(marker);const pixels=document.createElement('span');pixels.className='pixel-count';pixels.textContent=it.pixels+' px';b.appendChild(pixels);}}
 else {{const glyph=document.createElement('span');glyph.className='glyph-label';glyph.textContent='omatchad';b.appendChild(glyph);const pixels=document.createElement('span');pixels.className='pixel-count';pixels.textContent=it.pixels+' px';b.appendChild(pixels);}}
 b.onclick=()=>toggle(it.id);document.getElementById('items').appendChild(b);
}}
canvas.addEventListener('mousedown',e=>{{
 if(!pixelMode.checked)return;
 painting=true;erase=e.altKey;lastPaint=canvasPixel(e);paintPoint(lastPaint,erase);sync();e.preventDefault();
}});
canvas.addEventListener('mousemove',e=>{{
 if(!painting||!pixelMode.checked)return;
 const p=canvasPixel(e);paintLine(lastPaint,p,erase||e.altKey);lastPaint=p;sync();e.preventDefault();
}});
window.addEventListener('mouseup',()=>{{painting=false;lastPaint=null;}});
canvas.addEventListener('mouseleave',()=>{{if(!painting)lastPaint=null;}});
canvas.addEventListener('click',e=>{{
 if(pixelMode.checked)return;
 const p=canvasPixel(e);const hits=S.items.filter(it=>p.x>=it.bbox.left&&p.x<it.bbox.right&&p.y>=it.bbox.top&&p.y<it.bbox.bottom);if(hits.length)toggle(hits[hits.length-1].id);
}});
document.getElementById('clearPixels').onclick=()=>{{chosenPixels.clear();sync();}};
showGrid.addEventListener('change',draw);showBaseline.addEventListener('change',draw);pixelMode.addEventListener('change',draw);brushRadius.addEventListener('change',draw);img.onload=draw;
</script></body></html>'''


def main() -> int:
    ap = argparse.ArgumentParser(description="Open a local freehand pixel-mask editor for one exact SAOL row.")
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
            return legacy.load_review_state(args.jsonl, args.page, args.column, args.row, args.facit, args.threshold)

        def do_GET(self):
            if self.path != "/":
                self.send_error(404)
                return
            try:
                html = render_html(self._state(), message["text"]).encode("utf-8")
                message["text"] = ""
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(html)))
                self.end_headers()
                self.wfile.write(html)
            except Exception as exc:
                self.send_error(500, str(exc))

        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            form = parse_qs(self.rfile.read(length).decode("utf-8"), keep_blank_values=True)
            try:
                message["text"] = legacy.apply_edit(self._state(), args.facit, form)
            except Exception as exc:
                message["text"] = "FEL: " + str(exc)
            self.send_response(303)
            self.send_header("Location", "/")
            self.end_headers()

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
