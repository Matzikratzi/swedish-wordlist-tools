from __future__ import annotations

import re
import sys
from pathlib import Path

from . import ocr_manual_pixel_candidate_editor_v34 as v34


def main() -> int:
    argv = sys.argv[1:]
    out: Path | None = None
    if "--out" in argv:
        i = argv.index("--out")
        if i + 1 < len(argv):
            out = Path(argv[i + 1])

    rc = v34.main()
    if rc or out is None or not out.exists():
        return rc

    text = out.read_text(encoding="utf-8")

    # Keep a wider candidate pool than the final baseline gate.  We want one
    # raster scan, followed by cheap evaluation of neighbouring support lines.
    text = text.replace(
        "temp.baseline_distance_error=Math.abs(impliedBaseline-state.baseline);if(temp.baseline_distance_error>=2)continue;",
        "temp.baseline_distance_error=Math.abs(impliedBaseline-state.baseline);if(temp.baseline_distance_error>=4)continue;",
        1,
    )
    text = text.replace(
        "temp.baseline_distance_error=Math.abs(impliedBaseline-targetState.baseline);if(temp.baseline_distance_error>=2)continue;",
        "temp.baseline_distance_error=Math.abs(impliedBaseline-targetState.baseline);if(temp.baseline_distance_error>=4)continue;",
        1,
    )

    # Replace v33's per-candidate fixed exact bonus.  A tiny exact fragment must
    # not collect the same bonus as a large full glyph.  Exactness now scales
    # with explained ink, and each selected automatic glyph pays a small
    # fragmentation cost.  This makes one full n beat several half-lod pieces.
    weight_re = re.compile(
        r"const rel=relativeGlyphScore\(p\);const exact=.*?return p\.pixels\.size \+ 0\.45\*quality \+ 8\*rel \+ exactBonus - partialPenalty - \(Number\.isFinite\(\+p\.baseline_distance_error\)\?6\*Math\.abs\(\+p\.baseline_distance_error\):0\);"
    )
    new_weight = (
        "const rel=relativeGlyphScore(p);"
        "const exact=(+p.missing||0)===0 && (+p.extra||0)===0 && (!Number.isFinite(+p.total) || (+p.matched||p.pixels.size)>=(+p.total||p.pixels.size));"
        "const exactBonus=exact?0.45*p.pixels.size:0;"
        "const bbox=proposalBounds(p);let localInk=0;if(bbox){for(let y=bbox.ymin;y<=bbox.ymax;y++)for(let x=bbox.xmin;x<=bbox.xmax;x++)if(INK[y]&&INK[y][x])localInk++;}"
        "const coverage=localInk?Math.min(1,p.pixels.size/localInk):1;"
        "const partialPenalty=(1-coverage)*12;"
        "const fragmentPenalty=3.5;"
        "return p.pixels.size + 0.45*quality + 8*rel + exactBonus - partialPenalty - fragmentPenalty - (Number.isFinite(+p.baseline_distance_error)?6*Math.abs(+p.baseline_distance_error):0);"
    )
    if not weight_re.search(text):
        print("could not patch v36 glyph weight", file=sys.stderr)
        return 2
    text = weight_re.sub(new_weight, text, count=1)

    # Expose the beam objective so baseline alternatives can be compared without
    # regenerating glyph candidates.
    old_best = "const best=states[0]||{chosen:[]};\n const winners=new Set(best.chosen);"
    new_best = "const best=states[0]||{chosen:[],value:0,covered:0};\n state.lastRowScore=(best.value||0)+0.06*(best.covered||0);\n const winners=new Set(best.chosen);"
    if old_best not in text:
        print("could not expose v36 row score", file=sys.stderr)
        return 2
    text = text.replace(old_best, new_best, 1)

    # Install one global post-init pass immediately before the export handler.
    # At this point every card has already been constructed and registered in
    # allCards, so there is no fragile dependency on the historical card tail.
    export_anchor = "document.querySelector('#export').onclick=async()=>{"
    if export_anchor not in text:
        print("could not find v36 post-init anchor", file=sys.stderr)
        return 2

    post_init = r'''
function optimiseCardBaselineV36(card,proposals,state,INK){
 if(state.baselineManual)return {baseline:state.baseline,score:state.lastRowScore||0,tried:1};
 const W=+card.dataset.w,H=+card.dataset.h;
 const initial=state.baseline;
 let bestY=initial,bestScore=-Infinity,tried=0;
 const lo=Math.max(0,initial-2),hi=Math.min(H-1,initial+2);
 for(let y=lo;y<=hi;y++){
   state.baseline=y;
   resolveCandidateOverlaps(proposals,INK,W,H,state);
   const score=Number.isFinite(state.lastRowScore)?state.lastRowScore:-Infinity;
   tried++;
   if(score>bestScore+1e-9 || (Math.abs(score-bestScore)<=1e-9 && Math.abs(y-initial)<Math.abs(bestY-initial))){
     bestScore=score;bestY=y;
   }
 }
 state.baseline=bestY;
 state.baselineVotes=0;
 card.dataset.baseline=String(bestY);
 const b=card.querySelector('.baseline');if(b)b.value=bestY;
 resolveCandidateOverlaps(proposals,INK,W,H,state);
 state.autoBaselineInitial=initial;
 state.autoBaselineScore=bestScore;
 state.autoBaselineTried=tried;
 if(state.render)state.render();
 return {baseline:bestY,score:bestScore,tried};
}

// All card setup is complete here.  Optimise automatic support lines once,
// reusing the existing candidate pools.  No second raster scan is performed.
for(const [card,proposals,state,INK] of allCards){
 if(!state.baselineManual)optimiseCardBaselineV36(card,proposals,state,INK);
}
'''
    text = text.replace(export_anchor, post_init + "\n" + export_anchor, 1)

    # Recompute button: after rebuilding candidates, re-evaluate the support line
    # unless the human has explicitly chosen it.
    old_recompute = "const r=recomputeTargetCard(card,proposals,state,INK);\n   card.querySelector('.legend').textContent='Omräknat: '+r.added+' auto-kandidater · '+r.rejectedQuality+' under kvalitetsgräns · '+r.rejectedGap+' över hårt mellanrum';"
    new_recompute = "const r=recomputeTargetCard(card,proposals,state,INK);\n   let ob=null;if(!state.baselineManual)ob=optimiseCardBaselineV36(card,proposals,state,INK);\n   card.querySelector('.legend').textContent='Omräknat: '+r.added+' auto-kandidater'+(ob?' · stödlinje '+ob.baseline+' ('+ob.tried+' lägen)':'')+' · '+r.rejectedQuality+' under kvalitetsgräns · '+r.rejectedGap+' över hårt mellanrum';"
    if old_recompute not in text:
        print("could not patch v36 recompute baseline optimisation", file=sys.stderr)
        return 2
    text = text.replace(old_recompute, new_recompute, 1)

    text = text.replace("SAOL live-lärande pixelannotering v34", "SAOL live-lärande pixelannotering v36", 1)
    text = text.replace("corrected-v34.json", "corrected-v36.json")
    text = text.replace(
        "<b>Exakt helglyph prioriteras:</b>",
        "<b>Stödlinje + rad tolkas tillsammans:</b> när alla kort är färdigbyggda provar editorn högst fem stödlinjer (grov gissning ±2) mot samma kandidatpool och väljer den som ger bäst helradspoäng. Ingen ny glyphsökning görs för varje stödlinje. Exaktbonus skalar med mängden förklarat bläck och varje separat automatisk fragmentglyph kostar lite, så en hel bokstav ska slå flera små mallar inne i samma bläck. <b>Exakt helglyph prioriteras:</b>",
        1,
    )

    out.write_text(text, encoding="utf-8")
    print("v36: post-init joint baseline/row optimisation over at most 5 baselines; no fragile per-card injection")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
