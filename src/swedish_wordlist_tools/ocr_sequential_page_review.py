from __future__ import annotations

import argparse
import urllib.request
from pathlib import Path
from tempfile import NamedTemporaryFile

from PIL import Image

from . import ocr_exact_glyph_review_queue_v11 as review_v11
from . import ocr_prepare_sequential_page as sequential_page
from .ocr_glyph_facit_table import build_html as build_facit_html
from .ocr_glyph_matcher import load_facit
from .ocr_unique_unknown_glyph_review import build_html as build_unique_unknown_html, collect_candidates


def _safe_load_source_image(source: str) -> Image.Image | None:
    """Load a local page image or URL without treating an empty path as '.'."""
    if not source:
        return None

    local = Path(source)
    if local.is_file():
        return Image.open(local).convert("L")

    try:
        with urllib.request.urlopen(source, timeout=30) as response, NamedTemporaryFile(suffix=".png") as tmp:
            tmp.write(response.read())
            tmp.flush()
            return Image.open(tmp.name).convert("L")
    except Exception:
        return None


def _add_raster_text_ui(html: str) -> str:
    """Add a copyable text raster to every unique unknown-glyph card."""
    html = html.replace(
        ".badge{font-weight:700} .examples{margin-top:4px}",
        ".badge{font-weight:700} .examples{margin-top:4px} "
        ".rasterdump{display:none;white-space:pre;font:12px/1.05 monospace;background:#fafafa;border:1px solid #bbb;padding:8px;overflow:auto;max-width:100%;user-select:text}",
        1,
    )

    marker = "function stats(){const done=decisions.size;"
    helper = r'''function rasterText(c){
 const row=c.context;
 const ink=new Set((row.ink||[]).map(([x,y])=>pkey(x,y)));
 const exact=new Set(); for(const m of (row.exact||[]))for(const [x,y] of m.pixels)exact.add(pkey(x,y));
 const cur=new Set((row.candidate_pixels||[]).map(([x,y])=>pkey(x,y)));
 const lines=[];
 lines.push('unknown_id='+c.id+' occurrences='+c.occurrences);
 lines.push('examples='+c.sources.slice(0,8).map(s=>String(s.expected_word??'')+'@p'+String(s.page??'')).join(', '));
 lines.push('context_word='+String(row.expected??''));
 lines.push('size='+row.width+'x'+row.height+' baseline='+row.baseline);
 lines.push('candidate_shape_relative_to_baseline='+JSON.stringify(c.shape));
 lines.push('legend: #=other-unrecognized  X=known-exact  G=current-unknown  .=white');
 for(let y=0;y<row.height;y++){
   let s=String(y).padStart(2,'0')+' ';
   for(let x=0;x<row.width;x++){
     const k=pkey(x,y);
     s+=cur.has(k)?'G':(exact.has(k)?'X':(ink.has(k)?'#':'.'));
   }
   lines.push(s+(y===row.baseline?'  < baseline':''));
 }
 return lines.join('\n');
}
'''
    if marker not in html:
        raise RuntimeError("could not inject rasterText helper")
    html = html.replace(marker, helper + marker, 1)

    old_controls = '<button class="approve">Godkänn</button><button class="skip">Hoppa över</button><span class="msg"></span>'
    new_controls = '<button class="approve">Godkänn</button><button class="skip">Hoppa över</button><button class="raster">Rastertext</button><span class="msg"></span>'
    if old_controls not in html:
        raise RuntimeError("could not inject raster-text button")
    html = html.replace(old_controls, new_controls)

    old_input = "const input=ctrl.querySelector('input');ctrl.querySelector('.approve').onclick="
    new_input = r'''const input=ctrl.querySelector('input');
 const dump=document.createElement('pre');dump.className='rasterdump';d.appendChild(dump);
 ctrl.querySelector('.raster').onclick=async()=>{
   const text=rasterText(c);dump.textContent=text;dump.style.display='block';
   try{await navigator.clipboard.writeText(text);ctrl.querySelector('.msg').textContent='Rastertext visad och kopierad.';}
   catch(_){ctrl.querySelector('.msg').textContent='Rastertext visad; markera texten nedan för att kopiera.';}
 };
 ctrl.querySelector('.approve').onclick='''
    if old_input not in html:
        raise RuntimeError("could not inject raster-text handler")
    return html.replace(old_input, new_input, 1)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Read one SAOL facsimile page in sequence, accept all exact known glyphs, "
            "and build a review page containing only unique unexplained glyph rasters."
        )
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--page", type=int, default=1)
    ap.add_argument("--facit", type=Path, default=Path("glyphs/saol14-manual-glyph-facit.json"))
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--review-html", type=Path)
    ap.add_argument("--facit-html", type=Path)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--lang", default="swe")
    ap.add_argument("--psm", type=int, default=4)
    ap.add_argument("--pad-x", type=int, default=1)
    ap.add_argument("--pad-y", type=int, default=5)
    ap.add_argument("--min-confidence", type=float, default=-1.0)
    args = ap.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    review_html = args.review_html or (args.out_dir / "unknown-glyph-review.html")
    facit_html = args.facit_html or (args.out_dir / "glyph-facit-table.html")

    sequential_page._load_source_image = _safe_load_source_image
    report = sequential_page.prepare_page(
        args.jsonl,
        args.page,
        args.out_dir,
        threshold=args.threshold,
        lang=args.lang,
        psm=args.psm,
        pad_x=args.pad_x,
        pad_y=args.pad_y,
        min_confidence=args.min_confidence,
    )

    debug_files = sorted(args.out_dir.glob("saol14-word-debug-*.json"))
    if not debug_files:
        raise SystemExit("page preparation produced no word-debug files")

    models = load_facit(args.facit)
    analysed = [review_v11._analyse_one(path, models) for path in debug_files]
    exact = sum(1 for row in analysed if row.get("fully_exact"))
    incomplete = len(analysed) - exact
    candidates = collect_candidates(analysed)
    occurrences = sum(int(c.get("occurrences") or 0) for c in candidates)

    html = build_unique_unknown_html(analysed, args.facit)
    review_html.write_text(_add_raster_text_ui(html), encoding="utf-8")
    facit_html.write_text(build_facit_html(args.facit), encoding="utf-8")

    print(f"page={args.page}")
    print(f"source={report['source']}")
    print(f"ocr_words={len(debug_files)}")
    print(f"fully_exact={exact}")
    print(f"incomplete_words={incomplete}")
    print(f"unknown_occurrences={occurrences}")
    print(f"unique_unknown_rasters={len(candidates)}")
    print(f"review_html={review_html}")
    print(f"facit_html={facit_html}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
