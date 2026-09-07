from __future__ import annotations

import argparse
from pathlib import Path

from .ocr_exact_glyph_review_queue import _expand_inputs
from .ocr_exact_glyph_review_queue_v5 import build_html as build_html_v5
from .ocr_glyph_facit_table import build_html as build_facit_html


def build_html(paths: list[Path], facit_path: Path) -> str:
    html = build_html_v5(paths, facit_path)

    html = html.replace(
        "code{background:#eee;padding:1px 4px;border-radius:3px}",
        "code{background:#eee;padding:1px 4px;border-radius:3px} "
        ".rasterdump{display:none;white-space:pre;font:12px/1.05 monospace;background:#fafafa;border:1px solid #bbb;padding:8px;overflow:auto;max-width:100%;user-select:text}",
        1,
    )

    marker = "function styledLabel(label,style){return label+'{'+(styleShort[style]||'?')+'}';}"
    helper = marker + r'''
function rasterText(row,baseline){
 const ink=new Set(row.ink.map(([x,y])=>pkey(x,y)));
 const exact=new Set(); for(const m of row.exact)for(const [x,y] of m.pixels)exact.add(pkey(x,y));
 const lines=[];
 lines.push('word='+row.expected+' page='+String(row.page??'')+' subnr='+String(row.subnr??''));
 lines.push('size='+row.width+'x'+row.height+' baseline='+baseline+' baseline_source='+row.baseline_source);
 lines.push('recognized='+(row.recognized??row.exact.map(m=>m.label).join('')));
 lines.push('glyphs='+row.exact.map(m=>styledLabel(m.label,m.style)+'@x'+m.x).join(' '));
 lines.push('legend: #=black-unrecognized  X=black-recognized  .=white');
 for(let y=0;y<row.height;y++){
   let s=String(y).padStart(2,'0')+' ';
   for(let x=0;x<row.width;x++){
     const k=pkey(x,y); s+=exact.has(k)?'X':(ink.has(k)?'#':'.');
   }
   lines.push(s+(y===baseline?'  < baseline':''));
 }
 return lines.join('\n');
}'''
    if marker not in html:
        raise RuntimeError("could not inject rasterText helper")
    html = html.replace(marker, helper, 1)

    old_controls = "<button class=\"add\">Lägg till markerad variant</button><button class=\"clear\">Rensa markering</button><span class=\"msg\"></span>"
    new_controls = "<button class=\"add\">Lägg till markerad variant</button><button class=\"clear\">Rensa markering</button><button class=\"dump\">Rastertext</button><span class=\"msg\"></span>"
    if old_controls not in html:
        raise RuntimeError("could not inject raster dump button")
    html = html.replace(old_controls, new_controls, 1)

    old = "const labelInput=ctrl.querySelector('.label');"
    new = r'''const labelInput=ctrl.querySelector('.label');
 const dump=document.createElement('pre'); dump.className='rasterdump'; d.appendChild(dump);
 ctrl.querySelector('.dump').onclick=async()=>{
   const text=rasterText(row,baseline); dump.textContent=text; dump.style.display='block';
   try{await navigator.clipboard.writeText(text);ctrl.querySelector('.msg').textContent='Rastertext visad och kopierad.';}
   catch(_){ctrl.querySelector('.msg').textContent='Rastertext visad; markera texten nedan för att kopiera.';}
 };'''
    if old not in html:
        raise RuntimeError("could not inject raster dump handler")
    return html.replace(old, new, 1)


def main() -> int:
    ap = argparse.ArgumentParser(description="Generic exact-raster SAOL glyph OCR review with copyable text raster dumps.")
    ap.add_argument("inputs", nargs="+", type=Path)
    ap.add_argument("--facit", type=Path, default=Path("glyphs/saol14-manual-glyph-facit.json"))
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--facit-html", type=Path, default=Path("/tmp/glyph-facit-table.html"))
    args = ap.parse_args()
    files = _expand_inputs(args.inputs)
    if not files:
        raise SystemExit("no word-debug JSON files found")
    args.out.write_text(build_html(files, args.facit), encoding="utf-8")
    args.facit_html.write_text(build_facit_html(args.facit), encoding="utf-8")
    print(f"debug_files={len(files)}")
    print(args.out)
    print(f"facit_html={args.facit_html}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
