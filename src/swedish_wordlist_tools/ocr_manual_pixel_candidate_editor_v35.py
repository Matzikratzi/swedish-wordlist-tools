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

    old_weight = re.compile(
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
    if not old_weight.search(text):
        print("could not patch v35 glyph weight", file=sys.stderr)
        return 2
    text = old_weight.sub(new_weight, text, count=1)

    old_best = "const best=states[0]||{chosen:[]};\n const winners=new Set(best.chosen);"
    new_best = "const best=states[0]||{chosen:[],value:0,covered:0};\n state.lastRowScore=(best.value||0)+0.06*(best.covered||0);\n const winners=new Set(best.chosen);"
    if old_best not in text:
        print("could not expose v35 row score", file=sys.stderr)
        return 2
    text = text.replace(old_best, new_best, 1)

    anchor = "document.querySelectorAll('.card').forEach(card=>{"
    helper = r'''
function optimiseCardBaseline(card,proposals,state,INK,W,H){
 if(state.baselineManual)return {baseline:state.baseline,score:state.lastRowScore||0,tried:1};
 const initial=state.baseline;
 let bestY=initial,bestScore=-Infinity,tried=0;
 const lo=Math.max(0,initial-2),hi=Math.min(H-1,initial+2);
 for(let y=lo;y<=hi;y++){
   state.baseline=y;
   resolveCandidateOverlaps(proposals,INK,W,H,state);
   const score=Number.isFinite(state.lastRowScore)?state.lastRowScore:-Infinity;
   tried++;
   if(score>bestScore+1e-9 || (Math.abs(score-bestScore)<=1e-9 && Math.abs(y-initial)<Math.abs(bestY-initial))){bestScore=score;bestY=y;}
 }
 state.baseline=bestY;
 state.baselineVotes=0;
 card.dataset.baseline=String(bestY);
 const input=card.querySelector('.baseline');if(input)input.value=bestY;
 resolveCandidateOverlaps(proposals,INK,W,H,state);
 state.autoBaselineInitial=initial;
 state.autoBaselineScore=bestScore;
 return {baseline:bestY,score:bestScore,tried};
}
'''
    if anchor not in text:
        print("could not add v35 baseline optimiser", file=sys.stderr)
        return 2
    text = text.replace(anchor, helper + "\n" + anchor, 1)

    # The stable generated-card tail from v4 survives the later wrappers.  Hook
    # baseline optimisation immediately before the card's first final render,
    # after all handlers are installed and proposals are available.
    init = "if(state.selected!==null)card.querySelector('.label').value=proposals[state.selected].label;\n render();\n});"
    repl = "if(state.selected!==null)card.querySelector('.label').value=proposals[state.selected].label;\n if(!state.baselineManual){const ob=optimiseCardBaseline(card,proposals,state,INK,W,H);state.autoBaselineTried=ob.tried;}\n render();\n});"
    if init not in text:
        # v5+ clears the label input on selection; support that generated tail too.
        init2 = "if(state.selected!==null)card.querySelector('.label').value='';\n render();\n});"
        repl2 = "if(state.selected!==null)card.querySelector('.label').value='';\n if(!state.baselineManual){const ob=optimiseCardBaseline(card,proposals,state,INK,W,H);state.autoBaselineTried=ob.tried;}\n render();\n});"
        if init2 not in text:
            print("could not install v35 initial baseline optimisation", file=sys.stderr)
            return 2
        text = text.replace(init2, repl2, 1)
    else:
        text = text.replace(init, repl, 1)

    old_recompute = "const r=recomputeTargetCard(card,proposals,state,INK);\n   card.querySelector('.legend').textContent='Omräknat: '+r.added+' auto-kandidater · '+r.rejectedQuality+' under kvalitetsgräns · '+r.rejectedGap+' över hårt mellanrum';"
    new_recompute = "const r=recomputeTargetCard(card,proposals,state,INK);\n   let ob=null;if(!state.baselineManual)ob=optimiseCardBaseline(card,proposals,state,INK,+card.dataset.w,+card.dataset.h);\n   card.querySelector('.legend').textContent='Omräknat: '+r.added+' auto-kandidater'+(ob?' · stödlinje '+ob.baseline+' ('+ob.tried+' lägen)':'')+' · '+r.rejectedQuality+' under kvalitetsgräns · '+r.rejectedGap+' över hårt mellanrum';"
    if old_recompute not in text:
        print("could not patch v35 recompute baseline optimisation", file=sys.stderr)
        return 2
    text = text.replace(old_recompute, new_recompute, 1)

    text = text.replace("SAOL live-lärande pixelannotering v34", "SAOL live-lärande pixelannotering v35", 1)
    text = text.replace("corrected-v34.json", "corrected-v35.json")
    text = text.replace(
        "<b>Exakt helglyph prioriteras:</b>",
        "<b>Stödlinje + rad tolkas tillsammans:</b> editorn börjar från sin grova stödlinjegissning men provar sedan högst fem lägen (±2 rasterrader) mot samma kandidatpool och väljer den stödlinje som ger bäst helradspoäng. Detta görs utan fem nya glyphsökningar. Små exakta fragment får inte längre en fast bonus per fragment; exaktbonus skalar med förklarat bläck och varje vald fragmentglyph kostar lite, så ett helt n ska slå flera halvlodstreck inuti n. <b>Exakt helglyph prioriteras:</b>",
        1,
    )

    out.write_text(text, encoding="utf-8")
    print("v35: joint baseline/row optimisation over at most 5 baselines; proportional exact bonus and fragment penalty")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
