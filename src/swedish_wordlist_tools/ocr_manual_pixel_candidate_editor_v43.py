from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from . import ocr_manual_pixel_candidate_editor_v42 as v42


def main() -> int:
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("matches")
    ap.add_argument("library")
    ap.add_argument("--out", type=Path, required=True)
    args, _ = ap.parse_known_args(sys.argv[1:])

    rc = v42.main()
    if rc or not args.out.exists():
        return rc

    text = args.out.read_text(encoding="utf-8")

    # v30's beam resolver still gave every candidate roughly one point per
    # covered pixel.  That means a large mediocre candidate could beat several
    # smaller, much cleaner glyphs purely by size.  Replace the beam weight with
    # a deliberately quality-sensitive objective: size becomes a strong bonus
    # only when the raster match is exact or extremely close to exact.
    weight_re = re.compile(
        r" function weight\(p\)\{.*?\n \}",
        re.S,
    )
    new_weight = r''' function weight(p){
   const n=Math.max(1,p.pixels?p.pixels.size:0);
   const missing=Math.max(0,Number(p.missing||0));
   const extra=Math.max(0,Number(p.extra||0));
   const matched=Math.max(0,Number(p.matched ?? Math.max(0,n-missing)));
   const total=Math.max(1,Number(p.total ?? n));
   let rel=Number(p.relative_score);
   if(!Number.isFinite(rel))rel=Math.min(1,matched/total);
   rel=Math.max(0,Math.min(1,rel));
   const perfect=(missing===0 && extra===0 && matched===total && rel>=0.999999);

   let value;
   if(perfect){
     // Exact whole-raster matches are the gold standard.  Super-linear size
     // reward makes one genuine full glyph beat a mosaic of tiny subshapes.
     value=n + 1.55*Math.pow(n,1.6);
   }else{
     // Imperfect matches do NOT inherit the large-glyph size jackpot.
     // Coverage quality falls rapidly (fourth power), while every missing or
     // extra pixel further discounts the candidate.  Thus a broad 70–80%
     // resemblance cannot win merely because it covers many pixels.
     const quality=Math.pow(rel,4);
     const errorPenalty=1 + 0.40*(missing+extra);
     value=(n*quality)/errorPenalty;

     // Very-near-perfect candidates remain useful when no exact model exists,
     // but their size reward is intentionally modest compared with perfection.
     if(rel>=0.97 && missing+extra<=2)value += 0.20*Math.pow(n,1.35)*quality;
   }

   if(p.facit)value*=1.10;
   if(p.status==='manual')value*=1000;
   p.beamWeightV43=value;
   p.beamQualityV43=rel;
   p.beamErrorsV43=missing+extra;
   return value;
 }'''

    if not weight_re.search(text):
        print("could not replace v43 beam weight", file=sys.stderr)
        return 2
    text = weight_re.sub(new_weight, text, count=1)

    # Make v42's secondary full-glyph strength obey the same principle.  It is
    # used for post-pass dominance, so a large imperfect proposal must not gain
    # n^2 strength just by being large.
    strength_re = re.compile(
        r"function fullGlyphStrengthV42\(p\)\{.*?\n\}",
        re.S,
    )
    new_strength = r'''function fullGlyphStrengthV42(p){
 const n=Math.max(1,p.pixels?p.pixels.size:0);
 const perfect=proposalIsPerfectV42(p);
 const miss=Math.max(0,Number(p.missing||0)),extra=Math.max(0,Number(p.extra||0));
 const matched=Math.max(0,Number(p.matched ?? Math.max(0,n-miss)));
 const total=Math.max(1,Number(p.total ?? n));
 let rel=Number(p.relative_score);if(!Number.isFinite(rel))rel=Math.min(1,matched/total);rel=Math.max(0,Math.min(1,rel));
 let s;
 if(perfect)s=n + 1.55*Math.pow(n,1.6);
 else {
   const quality=Math.pow(rel,4);
   s=(n*quality)/(1+0.40*(miss+extra));
   if(rel>=0.97 && miss+extra<=2)s+=0.20*Math.pow(n,1.35)*quality;
 }
 if(p.facit)s*=1.10;
 if(p.status==='manual')s*=1000;
 return s;
}'''
    if not strength_re.search(text):
        print("could not replace v43 full-glyph strength", file=sys.stderr)
        return 2
    text = strength_re.sub(new_strength, text, count=1)

    text = text.replace("SAOL live-lärande pixelannotering v42", "SAOL live-lärande pixelannotering v43", 1)
    text = text.replace("corrected-v42.json", "corrected-v43.json")
    text = text.replace(
        "<b>Helglyph-dominans v42:</b>",
        "<b>Kvalitetsviktning v43:</b> storlek ger stor bonus bara vid perfekt eller nästan perfekt rastermatch. Perfekta glyphar premieras superlinjärt; ofullständiga stora träffar faller snabbt med täckningsgrad (fjärde potens) och straffas ytterligare per saknad/extra pixel. En stor ungefärlig träff kan därför inte vinna bara genom sin storlek. <b>Helglyph-dominans v42:</b>",
        1,
    )

    args.out.write_text(text, encoding="utf-8")
    print("v43: beam scoring is strongly quality-dependent; perfect large glyphs rewarded, imperfect large glyphs sharply discounted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
