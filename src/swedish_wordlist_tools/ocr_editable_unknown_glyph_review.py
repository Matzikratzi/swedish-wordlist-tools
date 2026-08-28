from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .ocr_unique_unknown_glyph_review import collect_candidates


def build_html(rows: list[dict[str, Any]], facit_path: Path) -> str:
    facit = json.loads(facit_path.read_text(encoding="utf-8"))
    candidates = collect_candidates(rows)
    payload = json.dumps({"candidates": candidates, "facit": facit}, ensure_ascii=False)
    return f"""<!doctype html>
<meta charset='utf-8'>
<title>SAOL – redigera okända glyphar</title>
<style>
body{{font-family:system-ui,sans-serif;margin:18px;background:#f4f4f4;color:#111}}
.top{{position:sticky;top:0;z-index:5;background:white;border:1px solid #bbb;padding:10px;margin-bottom:14px}}
.card{{background:white;border:1px solid #bbb;padding:12px;margin:12px 0}} .card.done{{opacity:.45}}
canvas{{image-rendering:pixelated;border:1px solid #888;background:white;display:block;margin:8px 0;cursor:crosshair}}
.controls{{display:flex;gap:8px;align-items:center;flex-wrap:wrap}} input,button{{font:inherit;padding:5px}}
.meta{{color:#555;font-size:.92em}} .hint{{margin:5px 0;padding:5px;background:#fff8d8;border-left:4px solid #d7a600}}
.rasterdump{{display:none;white-space:pre;font:12px/1.05 monospace;background:#fafafa;border:1px solid #bbb;padding:8px;overflow:auto;max-width:100%;user-select:text}}
</style>
<div class='top'><b>SAOL – redigera okända glyphar</b> <span id='stats'></span>
<button id='save'>Spara facit med godkända glyphar</button>
<div><small>Lila = redan känd glyph. Grönt = vår föreslagna pixelmarkering. Dra en ruta för att ersätta markeringen. Shift-dra lägger till svarta pixlar. Alt-dra tar bort. Dra den röda stödlinjen vid behov. JSONL-förslaget är bara förskrivet textförslag.</small></div></div>
<div id='cards'></div>
<script>
const DATA={payload}; const SCALE=12,M=2; const additions=[]; const decisions=new Map();
const keyOf=g=>JSON.stringify([g.label,g.style,g.pixels_relative_to_baseline]);
const known=new Set(DATA.facit.glyphs.map(keyOf));
const styleMap={{b:'bold',r:'roman',i:'italic'}};
const pkey=(x,y)=>x+','+y;
function esc(s){{return String(s??'').replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));}}
function parseLabel(raw){{const s=raw.trim();const m=s.match(/^(.*)\\{{([bri])\\}}$/i);if(!m)return null;return{{label:m[1],style:styleMap[m[2].toLowerCase()]}};}}
function stats(){{document.getElementById('stats').textContent=' · '+DATA.candidates.length+' kandidater · '+decisions.size+' behandlade · '+additions.length+' godkända';}}
function rasterText(c,selected,baseline){{const row=c.context;const exact=new Set();for(const m of row.exact||[])for(const [x,y] of m.pixels)exact.add(pkey(x,y));const ink=new Set((row.ink||[]).map(([x,y])=>pkey(x,y)));const lines=[];lines.push('unknown_id='+c.id+' occurrences='+c.occurrences);lines.push('jsonl_suggestion='+String(c.suggestion||'')+' support='+String(c.suggestion_support||0));lines.push('jsonl_hint='+JSON.stringify(row.jsonl_hint||{{}}));lines.push('page_word_bbox='+JSON.stringify(row.page_word_bbox||null));lines.push('context_word='+String(row.expected??''));lines.push('size='+row.width+'x'+row.height+' baseline='+baseline);lines.push('legend: #=other-unrecognized X=known-exact G=selected .=white');for(let y=0;y<row.height;y++){{let s=String(y).padStart(2,'0')+' ';for(let x=0;x<row.width;x++){{const k=pkey(x,y);s+=selected.has(k)?'G':(exact.has(k)?'X':(ink.has(k)?'#':'.'));}}lines.push(s+(y===baseline?'  < baseline':''));}}return lines.join('\\n');}}
const root=document.getElementById('cards');
for(const c of DATA.candidates){{
 const row=c.context,d=document.createElement('div');d.className='card';
 const hint=c.suggestion?'<div class="hint">JSONL-förslag: <b>'+esc(c.suggestion)+'</b> · stöd '+c.suggestion_support+'/'+c.occurrences+'</div>':'<div class="hint">Inget JSONL-förslag.</div>';
 d.innerHTML='<b>Okänd #'+c.id+'</b> <span class="meta">'+c.occurrences+' förekomst(er)</span>'+hint+'<div class="meta">OCR-kontext: '+esc(row.expected||'')+' · JSONL: '+esc((row.jsonl_hint||{{}}).text||'')+'</div>';
 let baseline=Number.isInteger(row.baseline)?row.baseline:Math.max(0,row.height-2),dragBaseline=false,dragRect=false,pixelMode=null,rect=null;
 const inkSet=new Set((row.ink||[]).map(([x,y])=>pkey(x,y))); const exactSet=new Set();for(const m of row.exact||[])for(const [x,y] of m.pixels)exactSet.add(pkey(x,y));
 const selected=new Set((row.candidate_pixels||[]).map(([x,y])=>pkey(x,y)));
 const canvas=document.createElement('canvas'),ctx=canvas.getContext('2d');canvas.width=(row.width+2*M)*SCALE;canvas.height=(row.height+2*M)*SCALE;d.appendChild(canvas);
 const baseY=()=>(baseline+1+M)*SCALE;
 function draw(){{ctx.fillStyle='#fff';ctx.fillRect(0,0,canvas.width,canvas.height);ctx.strokeStyle='#eee';ctx.lineWidth=1;for(let x=0;x<=row.width+2*M;x++){{const xx=x*SCALE+.5;ctx.beginPath();ctx.moveTo(xx,0);ctx.lineTo(xx,canvas.height);ctx.stroke();}}for(let y=0;y<=row.height+2*M;y++){{const yy=y*SCALE+.5;ctx.beginPath();ctx.moveTo(0,yy);ctx.lineTo(canvas.width,yy);ctx.stroke();}}for(const [x,y] of row.ink||[]){{const k=pkey(x,y);ctx.fillStyle=selected.has(k)?'#2a9d4b':(exactSet.has(k)?'#8f83d8':'#111');ctx.fillRect((x+M)*SCALE,(y+M)*SCALE,SCALE,SCALE);}}ctx.strokeStyle='#d33';ctx.lineWidth=3;ctx.beginPath();ctx.moveTo(0,baseY());ctx.lineTo(canvas.width,baseY());ctx.stroke();if(rect){{const x0=Math.min(rect.x0,rect.x1),x1=Math.max(rect.x0,rect.x1),y0=Math.min(rect.y0,rect.y1),y1=Math.max(rect.y0,rect.y1);ctx.strokeStyle='#080';ctx.lineWidth=2;ctx.strokeRect((x0+M)*SCALE,(y0+M)*SCALE,(x1-x0+1)*SCALE,(y1-y0+1)*SCALE);}}}}
 function pt(e){{const r=canvas.getBoundingClientRect();return{{x:Math.max(0,Math.min(row.width-1,Math.floor((e.clientX-r.left)/SCALE)-M)),y:Math.max(0,Math.min(row.height-1,Math.floor((e.clientY-r.top)/SCALE)-M)),cy:e.clientY-r.top}};}}
 function edit(p,mode){{const k=pkey(p.x,p.y);if(!inkSet.has(k))return;if(mode==='add')selected.add(k);else selected.delete(k);}}
 function fillRect(){{if(!rect)return;selected.clear();const x0=Math.min(rect.x0,rect.x1),x1=Math.max(rect.x0,rect.x1),y0=Math.min(rect.y0,rect.y1),y1=Math.max(rect.y0,rect.y1);for(const [x,y] of row.ink||[])if(x>=x0&&x<=x1&&y>=y0&&y<=y1)selected.add(pkey(x,y));}}
 canvas.onmousedown=e=>{{const p=pt(e);if(e.altKey||e.shiftKey){{pixelMode=e.altKey?'remove':'add';edit(p,pixelMode);draw();return;}}if(Math.abs(p.cy-baseY())<=Math.max(6,SCALE/2)){{dragBaseline=true;return;}}dragRect=true;rect={{x0:p.x,y0:p.y,x1:p.x,y1:p.y}};draw();}};
 canvas.onmousemove=e=>{{const p=pt(e);if(pixelMode){{edit(p,pixelMode);draw();return;}}if(dragBaseline){{baseline=Math.max(0,Math.min(row.height-1,Math.round(p.cy/SCALE-M-1)));draw();return;}}if(dragRect){{rect.x1=p.x;rect.y1=p.y;draw();}}}};
 canvas.onmouseup=()=>{{if(dragRect)fillRect();dragRect=false;dragBaseline=false;pixelMode=null;draw();}};canvas.onmouseleave=canvas.onmouseup;
 const ctrl=document.createElement('div');ctrl.className='controls';ctrl.innerHTML='<label>Etikett <input size="14" value="'+esc(c.suggestion||'')+'" placeholder=":{r}"></label><button class="approve">Godkänn markering</button><button class="reset">Återställ gissning</button><button class="skip">Hoppa över</button><button class="raster">Rastertext</button><span class="msg"></span>';d.appendChild(ctrl);
 const input=ctrl.querySelector('input'),msg=ctrl.querySelector('.msg'),dump=document.createElement('pre');dump.className='rasterdump';d.appendChild(dump);
 ctrl.querySelector('.reset').onclick=()=>{{selected.clear();for(const [x,y] of row.candidate_pixels||[])selected.add(pkey(x,y));baseline=row.baseline;rect=null;draw();}};
 ctrl.querySelector('.raster').onclick=async()=>{{const text=rasterText(c,selected,baseline);dump.textContent=text;dump.style.display='block';try{{await navigator.clipboard.writeText(text);msg.textContent='Rastertext kopierad.';}}catch(_){{msg.textContent='Rastertext visad.';}}}};
 ctrl.querySelector('.skip').onclick=()=>{{decisions.set(c.id,'skipped');d.classList.add('done');msg.textContent='Överhoppad.';stats();}};
 ctrl.querySelector('.approve').onclick=()=>{{const p=parseLabel(input.value);if(!p||!p.label||!selected.size){{msg.textContent='Skriv etikett med stil och markera minst en svart pixel.';return;}}const pts=[...selected].map(k=>k.split(',').map(Number));const minx=Math.min(...pts.map(p=>p[0]));const rel=pts.map(([x,y])=>[x-minx,y-baseline]).sort((a,b)=>a[0]-b[0]||a[1]-b[1]);const glyph={{label:p.label,style:p.style,pixels_relative_to_baseline:rel,sources:c.sources}};const k=keyOf(glyph);if(!known.has(k)&&!additions.some(a=>keyOf(a)===k))additions.push(glyph);decisions.set(c.id,'approved');d.classList.add('done');msg.textContent='Godkänd: '+p.label+' ('+rel.length+' pixlar).';stats();}};
 draw();root.appendChild(d);
}}
document.getElementById('save').onclick=()=>{{const out=structuredClone(DATA.facit);out.glyphs.push(...additions);out.glyphs.sort((a,b)=>a.style.localeCompare(b.style)||a.label.localeCompare(b.label)||JSON.stringify(a.pixels_relative_to_baseline).localeCompare(JSON.stringify(b.pixels_relative_to_baseline)));const blob=new Blob([JSON.stringify(out,null,2)+'\\n'],{{type:'application/json'}});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='saol14-manual-glyph-facit-reviewed.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);}};stats();
</script>"""
