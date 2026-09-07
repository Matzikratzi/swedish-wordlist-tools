from __future__ import annotations

import argparse
import html
import json
import random
import re
from pathlib import Path


TAG_RE = re.compile(r"<(/?)([a-zA-Z][^>]*)>")


def _strip_markup(value: object) -> str:
    return re.sub(r"<[^>]+>", "", str(value or ""))


def _seed_segments(entry: dict[str, object]) -> list[dict[str, str]]:
    """Return conservative typography hints. Never pretend unmarked `text` is known."""
    out: list[dict[str, str]] = []
    ordkl = str(entry.get("ordkl") or "")
    if ordkl:
        pos = 0
        style = "roman"
        for m in TAG_RE.finditer(ordkl):
            if m.start() > pos:
                out.append({"field": "ordkl", "text": ordkl[pos:m.start()], "style": style, "source": "markup"})
            closing, tag = m.group(1), m.group(2).lower().split()[0]
            if tag == "i":
                style = "roman" if closing else "italic"
            elif tag == "b":
                style = "roman" if closing else "bold"
            pos = m.end()
        if pos < len(ordkl):
            out.append({"field": "ordkl", "text": ordkl[pos:], "style": style, "source": "markup"})
    return [x for x in out if x["text"]]


def _load_entries(path: Path, limit: int, pages: set[int] | None, seed: int) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            e = json.loads(line)
            page = e.get("sidnr1")
            if pages and page not in pages:
                continue
            text = str(e.get("text") or "")
            if not text:
                continue
            rows.append({
                "subnr": e.get("subnr"),
                "page": page,
                "word": e.get("normaliserat_ord") or e.get("ord") or "",
                "ordkl_raw": e.get("ordkl") or "",
                "ordkl": _strip_markup(e.get("ordkl")),
                "text": text,
                "source": e.get("source") or "",
                "seeds": _seed_segments(e),
            })
    random.Random(seed).shuffle(rows)
    return rows[:limit]


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate a browser UI for manual SAOL typography annotation.")
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--pages", help="Comma-separated page numbers")
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()
    pages = {int(x) for x in args.pages.split(",") if x.strip()} if args.pages else None
    entries = _load_entries(args.jsonl, args.limit, pages, args.seed)
    payload = json.dumps(entries, ensure_ascii=False).replace("</", "<\\/")

    doc = f'''<!doctype html>
<meta charset="utf-8"><title>SAOL typografisk annotering</title>
<style>
*{{box-sizing:border-box}} body{{font-family:system-ui,sans-serif;margin:24px;background:#f5f5f5;color:#171717}} h1{{margin-bottom:.2rem}} .intro{{max-width:1000px;color:#444}} .toolbar{{position:sticky;top:0;z-index:4;background:#f5f5f5ee;padding:10px 0;display:flex;gap:8px;flex-wrap:wrap}}button{{font:inherit;padding:6px 10px;cursor:pointer}} .card{{background:white;border:1px solid #ccc;border-radius:9px;padding:14px;margin:14px 0;max-width:1100px}} .meta{{font-size:12px;color:#666;display:flex;gap:12px;flex-wrap:wrap}} .word{{font-size:20px;font-weight:700}} .field{{margin-top:10px}} .fieldname{{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:#777}} .annot{{font-family:Georgia,serif;font-size:22px;line-height:1.65;padding:8px;border:1px solid #ddd;border-radius:5px;white-space:pre-wrap}} .seed{{font-size:12px;color:#555;margin-top:5px}} .segments{{display:flex;gap:5px;flex-wrap:wrap;margin-top:8px}} .seg{{border-radius:4px;padding:3px 6px;font-size:13px}} .roman{{background:#e8eef7}} .italic{{background:#f4e6ff;font-style:italic}} .bold{{background:#ffe8d5;font-weight:700}} .special{{background:#e4f5e8}} .uncertain{{background:#fff4bf}} .status{{font-size:12px;color:#555}} a{{color:#0645ad}}
</style>
<h1>SAOL typografisk annotering</h1>
<p class="intro">Markera text med musen i <b>text</b>-rutan och klicka stil. Vi sparar exakt teckenintervall, så samma artikel kan innehålla flera stilar. <code>ordkl</code>-markup visas som ledtråd men förs inte automatiskt över till <code>text</code>. Allt sparas lokalt i webbläsaren tills du exporterar JSON.</p>
<div class="toolbar"><button data-style="roman">rak</button><button data-style="italic">kursiv</button><button data-style="bold">fet</button><button data-style="special">special</button><button data-style="uncertain">osäker</button><button id="undo">ångra senaste</button><button id="export">exportera annotations.json</button><span class="status" id="status"></span></div>
<div id="cards"></div>
<script>
const entries={payload}; const KEY='saol-typography-annotations-v1'; let anns=JSON.parse(localStorage.getItem(KEY)||'[]'); let last=null;
const esc=s=>s.replace(/[&<>]/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;'}}[c]));
function save(){{localStorage.setItem(KEY,JSON.stringify(anns));renderStatus();}}
function renderStatus(){{document.getElementById('status').textContent=anns.length+' sparade segment';}}
function card(e){{const seeds=e.seeds.map(s=>`<span class="seg ${{s.style}}">${{esc(s.text)}} → ${{s.style}}</span>`).join(''); return `<article class="card" data-subnr="${{e.subnr}}"><div class="word">${{esc(String(e.word))}}</div><div class="meta"><span>subnr ${{e.subnr}}</span><span>sida ${{e.page}}</span>${{e.source?`<a href="${{esc(String(e.source))}}" target="_blank">facsimil ↗</a>`:''}}</div><div class="field"><div class="fieldname">ordkl</div><div class="annot">${{esc(String(e.ordkl))}}</div><div class="seed">markup: ${{seeds||'ingen säker markup-ledtråd'}}</div></div><div class="field"><div class="fieldname">text — markera här</div><div class="annot target" data-field="text">${{esc(String(e.text))}}</div><div class="segments"></div></div></article>`}}
document.getElementById('cards').innerHTML=entries.map(card).join('');
function selectedRange(){{const sel=getSelection(); if(!sel||sel.rangeCount!==1||sel.isCollapsed)return null; const r=sel.getRangeAt(0); let node=r.commonAncestorContainer; if(node.nodeType===3)node=node.parentElement; const target=node.closest&&node.closest('.target'); if(!target)return null; const card=target.closest('.card'); const walker=document.createTreeWalker(target,NodeFilter.SHOW_TEXT); let start=0,end=0,pos=0,n; while(n=walker.nextNode()){{if(n===r.startContainer)start=pos+r.startOffset;if(n===r.endContainer)end=pos+r.endOffset;pos+=n.nodeValue.length}} if(end<start)[start,end]=[end,start]; const e=entries.find(x=>String(x.subnr)===card.dataset.subnr); return {{e,start,end,text:e.text.slice(start,end),field:target.dataset.field}};}}
document.querySelectorAll('[data-style]').forEach(b=>b.onclick=()=>{{const s=selectedRange();if(!s||!s.text)return alert('Markera först ett textstycke i TEXT-rutan.'); const a={{subnr:s.e.subnr,page:s.e.page,word:s.e.word,field:s.field,start:s.start,end:s.end,text:s.text,style:b.dataset.style,source:s.e.source}}; anns.push(a);last=a;save();getSelection().removeAllRanges();renderSegments();}});
function renderSegments(){{document.querySelectorAll('.card').forEach(c=>{{const box=c.querySelector('.segments');const xs=anns.filter(a=>String(a.subnr)===c.dataset.subnr);box.innerHTML=xs.map(a=>`<span class="seg ${{a.style}}">${{esc(a.text)}} → ${{a.style}}</span>`).join('')}})}}
document.getElementById('undo').onclick=()=>{{if(!anns.length)return;anns.pop();save();renderSegments();}};
document.getElementById('export').onclick=()=>{{const blob=new Blob([JSON.stringify({{version:1,annotations:anns}},null,2)],{{type:'application/json'}});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='saol14-typography-annotations.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);}};
renderSegments();renderStatus();
</script>'''
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(doc, encoding="utf-8")
    print(args.out)
    print(f"entries={len(entries)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
