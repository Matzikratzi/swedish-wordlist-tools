from __future__ import annotations

import argparse
from pathlib import Path

from .ocr_exact_glyph_review_queue import _expand_inputs
from .ocr_exact_glyph_review_queue_v2 import build_html as build_html_v2
from .ocr_glyph_facit_table import build_html as build_facit_html


def build_html(paths: list[Path], facit_path: Path) -> str:
    html = build_html_v2(paths, facit_path)
    old = """if(known.has(k)||additions.some(a=>keyOf(a)===k)){ctrl.querySelector('.msg').textContent='Den varianten finns redan.';return;}\n   additions.push(g);"""
    new = """if(known.has(k)){\n     // The model already exists, but it may have been missed because the user\n     // corrected the word baseline after the HTML was generated. Treat this\n     // manual selection as a confirmed placement on this card, not as a new\n     // facit model.\n     for(const [x,y] of pts) exactSet.add(pkey(x,y));\n     selected.clear(); rect=null; draw();\n     ctrl.querySelector('.msg').textContent='Finns redan i facit – placerad som '+styledLabel(label,style)+'.';\n     return;\n   }\n   if(additions.some(a=>keyOf(a)===k)){ctrl.querySelector('.msg').textContent='Den varianten är redan tillagd i denna omgång.';return;}\n   additions.push(g);"""
    if old not in html:
        raise RuntimeError("could not patch v2 known-glyph handling")
    return html.replace(old, new, 1)


def main() -> int:
    ap = argparse.ArgumentParser(description="Exact SAOL glyph review with manual placement of already-known models.")
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
