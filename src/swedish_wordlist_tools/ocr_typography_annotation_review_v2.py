from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

TAG_RE = re.compile(r"<(/?)([a-zA-Z][^>]*)>")
# These are lexicographic/metalinguistic labels, not inflected forms.  They are
# printed roman even when an upstream ordkl <i> span happens to contain them.
ROMAN_TOKEN_RE = re.compile(
    r"\b(?:s|adj|adv|v|vb|prep|pron|konj|interj|räkn|subst|verb|pl|best|pres|pret|sup|imper|inf|komp|superl|neutr|mask|fem|gen|dat|ack|nom|el|äv|sing|sg|pass|part|perf|presens|preteritum)\.",
    re.IGNORECASE,
)
TOKEN_RE = re.compile(r"\S+")


def _strip_markup(value: object) -> str:
    return re.sub(r"<[^>]+>", "", str(value or ""))


def _markup_spans(value: object) -> list[dict[str, str]]:
    raw = str(value or "")
    if not raw:
        return []
    out: list[dict[str, str]] = []
    pos = 0
    style = "roman"
    for m in TAG_RE.finditer(raw):
        if m.start() > pos:
            out.append({"text": raw[pos:m.start()], "style": style})
        closing, tag = m.group(1), m.group(2).lower().split()[0]
        if tag == "i":
            style = "roman" if closing else "italic"
        elif tag == "b":
            style = "roman" if closing else "bold"
        pos = m.end()
    if pos < len(raw):
        out.append({"text": raw[pos:], "style": style})
    return [s for s in out if s["text"]]


def _canon(s: str) -> str:
    return s.replace("+", "~").replace("–", "-").replace("—", "-").casefold()


def _is_roman_operator(token: str) -> bool:
    cleaned = token.strip(" ,;()[]")
    return bool(ROMAN_TOKEN_RE.fullmatch(cleaned))


def _find_token(text: str, token: str, used: list[tuple[int, int]]) -> tuple[int, int] | None:
    needle = _canon(token.strip(" ,;"))
    if not needle:
        return None
    hay = _canon(text)
    start = 0
    while True:
        i = hay.find(needle, start)
        if i < 0:
            return None
        j = i + len(needle)
        if not any(i < b and j > a for a, b in used):
            return i, j
        start = i + 1


def _token_bounds(m: re.Match[str]) -> tuple[int, int, str]:
    raw = m.group(0)
    left_trim = len(raw) - len(raw.lstrip(" ,;"))
    token = raw.strip(" ,;")
    a = m.start() + left_trim
    return a, a + len(token), token


def _auto_annotations(entry: dict[str, object]) -> list[dict[str, object]]:
    text = str(entry.get("text") or "")
    anns: list[dict[str, object]] = []

    # 1. Grammar wins.  Operators/labels are always roman, regardless of how
    # ordkl markup happened to group the surrounding inflection field.
    roman_ranges: list[tuple[int, int]] = []
    for m in ROMAN_TOKEN_RE.finditer(text):
        a, b = m.span()
        anns.append({"start": a, "end": b, "text": text[a:b], "style": "roman", "source": "operator", "confidence": "high"})
        roman_ranges.append((a, b))

    # Working SAOL convention: a token ending in ':' is a metalinguistic label,
    # not an inflected form.  Internal colon (a:et, abc:et) is NOT affected.
    for m in TOKEN_RE.finditer(text):
        a, b, token = _token_bounds(m)
        if token.endswith(":") and len(token) > 1:
            anns.append({"start": a, "end": b, "text": text[a:b], "style": "roman", "source": "colon-label", "confidence": "medium"})
            roman_ranges.append((a, b))

    # 2. ordkl markup supplies evidence about actual form values, but must not
    # relabel grammatical operators such as pl./best./el. as italic.
    used: list[tuple[int, int]] = list(roman_ranges)
    for span in _markup_spans(entry.get("ordkl")):
        if span["style"] not in {"italic", "bold"}:
            continue
        for raw in TOKEN_RE.findall(span["text"]):
            token = raw.strip(" ,;")
            if not token or _is_roman_operator(token) or token.endswith(":"):
                continue
            found = _find_token(text, token, used)
            if found:
                a, b = found
                anns.append({"start": a, "end": b, "text": text[a:b], "style": span["style"], "source": "ordkl-form", "confidence": "high"})
                used.append((a, b))

    # 3. The JSONL `text` field is the inflection/form string.  Once explicit
    # roman labels have been carved out, remaining lexical/form tokens are
    # normally italic.  This catches a:et, a:n, a, a:na, full plural forms,
    # repetition marks, + forms and -suffix forms even when markup is missing.
    for m in TOKEN_RE.finditer(text):
        a, b, token = _token_bounds(m)
        if not token or _is_roman_operator(token) or token.endswith(":"):
            continue
        # Ignore punctuation-only material; separators remain unclassified.
        if not any(ch.isalnum() for ch in token) and not any(ch in "+~-" for ch in token):
            continue
        if any(a < rb and b > ra for ra, rb in roman_ranges):
            continue
        if any(a == int(x["start"]) and b == int(x["end"]) for x in anns):
            continue
        anns.append({"start": a, "end": b, "text": text[a:b], "style": "italic", "source": "form-field", "confidence": "medium"})

    # Exact-range dedupe.  Manual corrections in the browser still override all
    # automatic annotations when rendering/exporting.
    rank = {"high": 2, "medium": 1, "low": 0}
    best: dict[tuple[int, int], dict[str, object]] = {}
    for ann in anns:
        key = (int(ann["start"]), int(ann["end"]))
        if key not in best or rank[str(ann["confidence"])] > rank[str(best[key]["confidence"])]:
            best[key] = ann
    return sorted(best.values(), key=lambda x: (int(x["start"]), int(x["end"])))


def _load_all(path: Path) -> dict[int, list[dict[str, object]]]:
    by_page: dict[int, list[dict[str, object]]] = defaultdict(list)
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            e = json.loads(line)
            text = e.get("text")
            page = e.get("sidnr1")
            if not isinstance(text, str) or not text.strip() or not isinstance(page, int):
                continue
            by_page[page].append(e)
    return by_page


def _choose_page(by_page: dict[int, list[dict[str, object]]], requested: int | None, limit: int) -> int:
    if requested is not None:
        if requested not in by_page:
            raise SystemExit(f"No eligible non-null text entries on page {requested}")
        return requested
    for page in sorted(by_page):
        if len(by_page[page]) >= limit:
            return page
    if not by_page:
        raise SystemExit("No eligible entries")
    return max(by_page, key=lambda p: len(by_page[p]))


def main() -> int:
    ap = argparse.ArgumentParser(description="Preannotated single-page SAOL typography review.")
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--limit", type=int, default=30)
    ap.add_argument("--page", type=int, help="Facsimile page; default chooses one page with enough eligible entries")
    args = ap.parse_args()

    by_page = _load_all(args.jsonl)
    page = _choose_page(by_page, args.page, args.limit)
    raw_entries = by_page[page][: args.limit]
    entries: list[dict[str, object]] = []
    for e in raw_entries:
        entries.append({
            "subnr": e.get("subnr"),
            "page": page,
            "word": e.get("normaliserat_ord") or e.get("ord") or "",
            "ordkl_raw": e.get("ordkl") or "",
            "ordkl": _strip_markup(e.get("ordkl")),
            "text": e["text"],
            "source": e.get("source") or "",
            "markup_spans": _markup_spans(e.get("ordkl")),
            "auto": _auto_annotations(e),
        })
    payload = json.dumps(entries, ensure_ascii=False).replace("</", "<\\/")

    doc = f'''<!doctype html><meta charset="utf-8"><title>SAOL typografi – förmarkerad</title>
<style>
*{{box-sizing:border-box}}body{{font-family:system-ui,sans-serif;margin:24px;background:#f5f5f5;color:#171717}}h1{{margin-bottom:.2rem}}.intro{{max-width:1050px;color:#444}}.toolbar{{position:sticky;top:0;z-index:5;background:#f5f5f5ee;padding:9px 0;display:flex;gap:7px;flex-wrap:wrap}}button{{font:inherit;padding:6px 10px;cursor:pointer}}.card{{background:#fff;border:1px solid #ccc;border-radius:9px;padding:14px;margin:14px 0;max-width:1120px}}.meta{{font-size:12px;color:#666;display:flex;gap:12px;flex-wrap:wrap}}.word{{font-weight:700;font-size:20px}}.fieldname{{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:#777;margin-top:9px}}.target,.preview{{font-family:Georgia,serif;font-size:22px;line-height:1.65;padding:8px;border:1px solid #ddd;border-radius:5px;white-space:pre-wrap}}.preview span{{border-radius:3px;padding:1px 0}}.roman{{background:#dfeafa}}.italic{{background:#efdfff;font-style:italic}}.bold{{background:#ffe1ca;font-weight:700}}.special{{background:#dff3e4}}.uncertain{{background:#fff2b5}}.chips{{display:flex;gap:5px;flex-wrap:wrap;margin-top:6px}}.chip{{font-size:12px;padding:3px 6px;border-radius:4px}}.manual{{outline:2px solid #222}}.status{{font-size:12px;color:#555}}a{{color:#0645ad}}
</style>
<h1>SAOL typografi – sida {page}</h1><p class="intro">Alla {len(entries)} artiklar kommer från samma faksimilsida. Förmarkeringen använder nu SAOL-grammatiken först: operatorer som <code>pl.</code>, <code>best.</code> och <code>el.</code> är raka; själva formvärdena i <code>text</code> är kursiva om inget starkare säger annat. <code>ordkl</code>-markup används som extra formbevis, men får aldrig göra en grammatisk operator kursiv. Markera bara det jag fortfarande fått fel.</p>
<div class="toolbar"><button data-style="roman">rak</button><button data-style="italic">kursiv</button><button data-style="bold">fet</button><button data-style="special">special</button><button data-style="uncertain">osäker</button><button id="undo">ångra</button><button id="export">exportera korrigeringar</button><span id="status" class="status"></span></div><div id="cards"></div>
<script>
const entries={payload};const KEY='saol-typography-corrections-v3-page-{page}';let manual=JSON.parse(localStorage.getItem(KEY)||'[]');
const esc=s=>s.replace(/[&<>]/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;'}}[c]));
function effective(e){{return [...e.auto,...manual.filter(a=>String(a.subnr)===String(e.subnr)).map(a=>({{...a,source:'manual',confidence:'manual'}}))];}}
function preview(e){{let marks=effective(e);let cuts=new Set([0,e.text.length]);marks.forEach(a=>{{cuts.add(a.start);cuts.add(a.end)}});let xs=[...cuts].sort((a,b)=>a-b),out='';for(let i=0;i<xs.length-1;i++){{let a=xs[i],b=xs[i+1],seg=e.text.slice(a,b);let hits=marks.filter(x=>a>=x.start&&b<=x.end);let m=hits.filter(x=>x.source==='manual').at(-1)||hits.sort((x,y)=>(y.confidence==='high')-(x.confidence==='high')).at(-1);out+=m?`<span class="${{m.style}} ${{m.source==='manual'?'manual':''}}" title="${{esc(m.source)}}">${{esc(seg)}}</span>`:esc(seg)}}return out;}}
function card(e){{let chips=e.auto.map(a=>`<span class="chip ${{a.style}}">${{esc(a.text)}} → ${{a.style}} (${{a.source}})</span>`).join('');return `<article class="card" data-subnr="${{e.subnr}}"><div class="word">${{esc(String(e.word))}}</div><div class="meta"><span>subnr ${{e.subnr}}</span><span>sida ${{e.page}}</span>${{e.source?`<a href="${{esc(String(e.source))}}" target="_blank">samma faksimil ↗</a>`:''}}</div><div class="fieldname">ordkl</div><div>${{esc(String(e.ordkl))}}</div><div class="fieldname">min förmarkering</div><div class="preview">${{preview(e)}}</div><div class="chips">${{chips}}</div><div class="fieldname">rå text – markera bara det som är fel</div><div class="target" data-field="text">${{esc(e.text)}}</div></article>`}}
function render(){{document.getElementById('cards').innerHTML=entries.map(card).join('');document.getElementById('status').textContent=manual.length+' manuella korrigeringar';}}
function selected(){{const sel=getSelection();if(!sel||sel.rangeCount!==1||sel.isCollapsed)return null;const r=sel.getRangeAt(0);let n=r.commonAncestorContainer;if(n.nodeType===3)n=n.parentElement;const t=n.closest&&n.closest('.target');if(!t)return null;const c=t.closest('.card'),e=entries.find(x=>String(x.subnr)===c.dataset.subnr);const w=document.createTreeWalker(t,NodeFilter.SHOW_TEXT);let pos=0,start=0,end=0,x;while(x=w.nextNode()){{if(x===r.startContainer)start=pos+r.startOffset;if(x===r.endContainer)end=pos+r.endOffset;pos+=x.nodeValue.length}}if(end<start)[start,end]=[end,start];return{{e,start,end,text:e.text.slice(start,end)}}}}
document.querySelectorAll('[data-style]').forEach(b=>b.onclick=()=>{{const s=selected();if(!s||!s.text)return alert('Markera först det felaktiga segmentet i råtexten.');manual.push({{subnr:s.e.subnr,page:s.e.page,start:s.start,end:s.end,text:s.text,style:b.dataset.style}});localStorage.setItem(KEY,JSON.stringify(manual));getSelection().removeAllRanges();render();}});
document.getElementById('undo').onclick=()=>{{manual.pop();localStorage.setItem(KEY,JSON.stringify(manual));render();}};
document.getElementById('export').onclick=()=>{{const blob=new Blob([JSON.stringify({{version:3,page:{page},corrections:manual,auto:entries.map(e=>({{subnr:e.subnr,annotations:e.auto}}))}},null,2)],{{type:'application/json'}});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='saol14-typography-corrections-page-{page}.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)}};render();
</script>'''
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(doc, encoding="utf-8")
    print(args.out)
    print(f"page={page} entries={len(entries)} auto_annotations={sum(len(e['auto']) for e in entries)}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
