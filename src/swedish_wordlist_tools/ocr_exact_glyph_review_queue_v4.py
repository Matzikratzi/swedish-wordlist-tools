from __future__ import annotations

import argparse
from pathlib import Path

from .ocr_exact_glyph_review_queue import _expand_inputs
from .ocr_exact_glyph_review_queue_v3 import build_html as build_html_v3
from .ocr_glyph_facit_table import build_html as build_facit_html


def build_html(paths: list[Path], facit_path: Path) -> str:
    html = build_html_v3(paths, facit_path)

    old = "const DATA="
    if old not in html:
        raise RuntimeError("could not find DATA declaration")

    html = html.replace(
        "const DATA=",
        "const DATA=",
        1,
    )

    html = html.replace(
        "const DATA=",
        "const DATA=",
        1,
    )

    # Keep a separate list of confirmed placements of models that already exist
    # in facit. These are not new glyph models and therefore must not be merged
    # into facit.glyphs.
    html = html.replace(
        "const DATA=",
        "const DATA=",
        1,
    )
    marker = "const cards=document.getElementById('cards');"
    if marker not in html:
        raise RuntimeError("could not patch placement state")
    html = html.replace(
        marker,
        "const placements=[];\n" + marker,
        1,
    )

    # Re-apply persisted placements for this exact source word when rendering.
    old_exact = "const exactSet=new Set(); for(const m of row.exact)for(const [x,y] of m.pixels)exactSet.add(pkey(x,y));"
    new_exact = """const exactSet=new Set(); for(const m of row.exact)for(const [x,y] of m.pixels)exactSet.add(pkey(x,y));
 const sourceKey=p=>String(p.page??'')+'|'+String(p.subnr??'')+'|'+String(p.expected_word??p.expected??'');
 const rowKey=String(row.page??'')+'|'+String(row.subnr??'')+'|'+String(row.expected??'');
 for(const p of (DATA.facit.placements||[])){
   if(sourceKey(p)!==rowKey)continue;
   for(const [x,y] of (p.pixels||[]))exactSet.add(pkey(x,y));
 }"""
    if old_exact not in html:
        raise RuntimeError("could not patch persisted placement loading")
    html = html.replace(old_exact, new_exact, 1)

    # Replace v3's transient known-glyph behaviour with persistent placement.
    old_known = """if(known.has(k)){
     // The model already exists, but it may have been missed because the user
     // corrected the word baseline after the HTML was generated. Treat this
     // manual selection as a confirmed placement on this card, not as a new
     // facit model.
     for(const [x,y] of pts) exactSet.add(pkey(x,y));
     selected.clear(); rect=null; draw();
     ctrl.querySelector('.msg').textContent='Finns redan i facit – placerad som '+styledLabel(label,style)+'.';
     return;
   }"""
    new_known = """if(known.has(k)){
     for(const [x,y] of pts) exactSet.add(pkey(x,y));
     const placement={
       page:row.page,subnr:row.subnr,expected_word:row.expected,
       label,style,baseline,pixels:pts.map(([x,y])=>[x,y])
     };
     const pk=JSON.stringify([placement.page,placement.subnr,placement.expected_word,placement.label,placement.style,placement.baseline,placement.pixels]);
     const persisted=(DATA.facit.placements||[]).some(p=>JSON.stringify([p.page,p.subnr,p.expected_word,p.label,p.style,p.baseline,p.pixels])===pk);
     const staged=placements.some(p=>JSON.stringify([p.page,p.subnr,p.expected_word,p.label,p.style,p.baseline,p.pixels])===pk);
     if(!persisted&&!staged)placements.push(placement);
     selected.clear(); rect=null; draw();
     ctrl.querySelector('.msg').textContent='Finns redan i facit – placeringen sparas för '+styledLabel(label,style)+'.';
     return;
   }"""
    if old_known not in html:
        raise RuntimeError("could not patch known placement persistence")
    html = html.replace(old_known, new_known, 1)

    # Merge staged placements into the downloaded facit JSON.
    old_save = "const out=structuredClone(DATA.facit);out.glyphs.push(...additions);"
    new_save = """const out=structuredClone(DATA.facit);out.glyphs.push(...additions);
  out.placements=out.placements||[];
  for(const p of placements){
    const pk=JSON.stringify([p.page,p.subnr,p.expected_word,p.label,p.style,p.baseline,p.pixels]);
    if(!out.placements.some(q=>JSON.stringify([q.page,q.subnr,q.expected_word,q.label,q.style,q.baseline,q.pixels])===pk))out.placements.push(p);
  }"""
    if old_save not in html:
        raise RuntimeError("could not patch save placement merge")
    html = html.replace(old_save, new_save, 1)

    return html


def main() -> int:
    ap = argparse.ArgumentParser(description="Exact SAOL glyph review with persistent per-word placements of already-known glyphs.")
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
