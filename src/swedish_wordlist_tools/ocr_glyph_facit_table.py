from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

FACIT_FORMATS = {"saol14-manual-glyph-facit-v1", "saol14-manual-glyph-facit-v2"}
ROLE_ORDER = [
    "unknown",
    "headword-bold",
    "pos-roman",
    "inflection-italic",
    "context-italic",
    "definition-roman",
    "inflection-label-roman",
]
ROLE_LABEL = {
    "unknown": "Okänd roll",
    "headword-bold": "Huvudord",
    "pos-roman": "Ordklass",
    "inflection-italic": "Böjning",
    "context-italic": "Kontext/exempel",
    "definition-roman": "Definition",
    "inflection-label-roman": "Böjningsetikett",
}


def load_facit(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("format") not in FACIT_FORMATS:
        raise ValueError(f"unsupported facit format: {payload.get('format')!r}")
    return payload


def _sort_key(label: str) -> tuple:
    order = "abcdefghijklmnopqrstuvwxyzåäö"
    if label and label[0].lower() in order:
        return (1, order.index(label[0].lower()), label.lower(), label)
    return (0, label)


def _role(glyph: dict[str, Any], facit_format: str) -> str:
    if facit_format == "saol14-manual-glyph-facit-v2":
        return str(glyph.get("role") or "unknown")
    return str(glyph.get("style") or "roman")


def build_html(facit_path: Path) -> str:
    facit = load_facit(facit_path)
    fmt = str(facit.get("format"))
    groups: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    all_ys: list[int] = []
    roles_seen: set[str] = set()
    for glyph in facit.get("glyphs") or []:
        label = str(glyph.get("label") or "")
        if not label:
            continue
        role = _role(glyph, fmt)
        groups[label][role].append(glyph)
        roles_seen.add(role)
        all_ys.extend(int(y) for _, y in glyph.get("pixels_relative_to_baseline") or [])

    if fmt.endswith("v2"):
        roles = [r for r in ROLE_ORDER if r in roles_seen] + sorted(roles_seen - set(ROLE_ORDER))
    else:
        roles = [r for r in ("bold", "roman", "italic") if r in roles_seen]
    labels = sorted(groups, key=_sort_key)
    payload = {
        "labels": labels,
        "groups": groups,
        "roles": roles,
        "role_labels": ROLE_LABEL,
        "global_min_y": min(all_ys + [-2]),
        "global_max_y": max(all_ys + [2]),
        "facit": facit,
    }
    data = json.dumps(payload, ensure_ascii=False)

    return f"""<!doctype html>
<meta charset='utf-8'>
<title>SAOL glyphfacit</title>
<style>
body{{font-family:system-ui,sans-serif;margin:20px;background:#f6f6f6;color:#111}}
h1{{margin:0 0 8px}} .meta{{color:#555;margin-bottom:12px}}
.role{{background:white;border:1px solid #bbb;margin:16px 0;padding:12px}}
.role h2{{margin:0 0 10px;font-size:18px}} .glyphs{{display:flex;flex-wrap:wrap;gap:14px;align-items:flex-start}}
.item{{display:flex;gap:7px;align-items:flex-start;border-right:1px solid #ddd;padding-right:12px}} .label{{font-size:22px;font-weight:700;min-width:26px}}
.variants{{display:flex;gap:8px}} .variant{{display:flex;flex-direction:column;align-items:flex-start}} .cap{{font-size:10px;color:#666}}
canvas{{image-rendering:pixelated;display:block;background:white}} .sources{{font-size:9px;color:#666;max-width:150px}}
</style>
<h1>SAOL glyphfacit</h1>
<div class='meta'>V2 skiljer bokstavlig rasterform från semantisk typografiroll. Migrerade v1-raster visas under <b>Okänd roll</b> tills rollen verifierats på nytt.</div>
<div id='root'></div>
<script>
const DATA={data}; const SCALE=8,PADX=2,PADY=2; const MINY=DATA.global_min_y,MAXY=DATA.global_max_y,H=MAXY-MINY+1;
function draw(canvas,g){{const pts=g.pixels_relative_to_baseline||[];if(!pts.length)return;const xs=pts.map(p=>p[0]),minx=Math.min(...xs),maxx=Math.max(...xs),w=maxx-minx+1;canvas.width=(w+2*PADX)*SCALE;canvas.height=(H+2*PADY)*SCALE;const c=canvas.getContext('2d');c.fillStyle='#fff';c.fillRect(0,0,canvas.width,canvas.height);for(const [x,y] of pts){{c.fillStyle='#111';c.fillRect((x-minx+PADX)*SCALE,(y-MINY+PADY)*SCALE,SCALE,SCALE);}}const by=(0-MINY+PADY+1)*SCALE;c.strokeStyle='#d33';c.lineWidth=1;c.beginPath();c.moveTo(0,by);c.lineTo(canvas.width,by);c.stroke();}}
function roleName(r){{return DATA.role_labels[r]||r;}}
const root=document.getElementById('root');
for(const role of DATA.roles){{const sec=document.createElement('section');sec.className='role';const h=document.createElement('h2');h.textContent=roleName(role)+' · '+role;sec.appendChild(h);const box=document.createElement('div');box.className='glyphs';for(const label of DATA.labels){{const models=(DATA.groups[label]&&DATA.groups[label][role])||[];if(!models.length)continue;const item=document.createElement('div');item.className='item';const lab=document.createElement('div');lab.className='label';lab.textContent=label;item.appendChild(lab);const vs=document.createElement('div');vs.className='variants';models.forEach((g,i)=>{{const v=document.createElement('div');v.className='variant';const cap=document.createElement('div');cap.className='cap';cap.textContent=models.length>1?'v'+(i+1):'';v.appendChild(cap);const cv=document.createElement('canvas');draw(cv,g);v.appendChild(cv);const s=document.createElement('div');s.className='sources';const legacy=g.legacy_style?('tidigare '+g.legacy_style):'';s.textContent=legacy;v.appendChild(s);vs.appendChild(v);}});item.appendChild(vs);box.appendChild(item);}}sec.appendChild(box);root.appendChild(sec);}}
</script>"""


def main() -> int:
    ap = argparse.ArgumentParser(description="Render canonical SAOL glyph facit grouped by typography role.")
    ap.add_argument("facit", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    args.out.write_text(build_html(args.facit), encoding="utf-8")
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
