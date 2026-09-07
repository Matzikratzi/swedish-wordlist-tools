from __future__ import annotations

import re
import sys
from pathlib import Path

from . import ocr_manual_pixel_candidate_editor_v26 as v26


def main() -> int:
    argv = sys.argv[1:]
    out: Path | None = None
    if "--out" in argv:
        i = argv.index("--out")
        if i + 1 < len(argv):
            out = Path(argv[i + 1])

    rc = v26.main()
    if rc or out is None or not out.exists():
        return rc

    text = out.read_text(encoding="utf-8")

    # v25 translated annotation pixels when the human changed the baseline.
    # That is wrong once a candidate has already been registered to source ink:
    # source pixels are evidence and must never move merely because our baseline
    # estimate changes.  A baseline edit changes only the coordinate reference.
    old_handler = re.compile(
        r"const b=card\.querySelector\('\.baseline'\);\n"
        r"b\.onchange=\(\)=>\{\n"
        r" const oldBaseline=state\.baseline;.*?\n\};",
        re.S,
    )
    new_handler = r'''const b=card.querySelector('.baseline');
b.onchange=()=>{
 const newBaseline=Math.max(0,Math.min(H-1,+b.value));
 state.baseline=newBaseline;
 state.baselineManual=true;
 state.baselineVotes=0;
 card.dataset.baseline=String(newBaseline);
 b.value=newBaseline;
 // IMPORTANT: proposals stay on the same absolute source-ink pixels.
 // Export recomputes pixels_relative_to_baseline from the new baseline.
 render();
};'''
    if not old_handler.search(text):
        print("could not replace v27 manual baseline handler", file=sys.stderr)
        return 2
    text = old_handler.sub(new_handler, text, count=1)

    # Replace the fuzzy propagator with ink-first registration.  The old matcher
    # chose y from target baseline first and searched only +/-1 row.  That lets a
    # wrong target baseline pull an otherwise good glyph away from the raster.
    # Here every feasible y/x placement is scored against actual black pixels.
    # A good placement then carries the baseline it implies from the learned
    # glyph's baselineOffset; baseline is downstream evidence, never placement.
    prop_re = re.compile(
        r"function propagateFinished\(sourceCard,sourceProposal,sourceState\)\{.*?\n\}",
        re.S,
    )
    new_prop = r'''function propagateFinished(sourceCard,sourceProposal,sourceState){
 if(!sourceProposal || sourceProposal.status!=='manual' || !sourceProposal.label || !sourceProposal.pixels.size)return 0;
 const sourceStyle=proposalStyle(sourceProposal,sourceCard);
 const model=normManualShape(sourceProposal.pixels,sourceState.baseline);if(!model)return 0;
 let added=0;
 for(const tuple of allCards){
   const [card,proposals,state,INK]=tuple;
   if(card===sourceCard)continue;
   const W=+card.dataset.w,H=+card.dataset.h;
   for(let y0=0;y0+model.height<=H;y0++){
     for(let x0=0;x0+model.width<=W;x0++){
       const abs=new Set();let matched=0,missing=0,extra=0;
       const expected=new Set(model.shape.map(([dx,ddy])=>(x0+dx)+','+(y0+ddy)));
       for(const [dx,ddy] of model.shape){
         const x=x0+dx,y=y0+ddy;
         if(INK[y]&&INK[y][x]){matched++;abs.add(x+','+y)}else missing++;
       }
       for(let y=y0;y<y0+model.height;y++)for(let x=x0;x<x0+model.width;x++){
         if(INK[y]&&INK[y][x]&&!expected.has(x+','+y))extra++;
       }
       const total=model.shape.length;
       const missRatio=missing/Math.max(1,total),extraRatio=extra/Math.max(1,total);
       if(matched<3 || missRatio>.25 || extraRatio>.35)continue;
       // Coverage dominates.  Baseline is deliberately absent from this score.
       const score=matched-2*missing-extra;
       if(score<=0)continue;
       if(proposals.some(p=>p.label===sourceProposal.label && proposalStyle(p,card)===sourceStyle && samePixelSet(p.pixels,abs)))continue;
       const context=hasDetachedContextInk(INK,W,H,x0,y0,model.width,model.height,abs);
       const impliedBaseline=y0+model.baselineOffset;
       proposals.push({label:sourceProposal.label,style:sourceStyle,status:(missing||extra||context)?'propagated-context':'propagated-exact',pixels:abs,contacts:[],external_contacts:0,missing,extra,score,matched,total,propagated_from:sourceCard.dataset.subnr,baseline_hint:impliedBaseline,baseline_dy:impliedBaseline-state.baseline});
       added++;
     }
   }
   if(added)state._needsRender=true;
 }
 for(const [card,proposals,state] of allCards){if(state.render)state.render();state._needsRender=false}
 return added;
}'''
    if not prop_re.search(text):
        print("could not replace v27 ink-first propagation", file=sys.stderr)
        return 2
    text = prop_re.sub(new_prop, text, count=1)

    # Automatic candidates already know the baseline implied by the source
    # glyph's learned baseline offset.  Use that vote directly. Manual glyphs
    # still fall back to geometric baselineVoteY().
    old_vote = "const y=baselineVoteY(p,style);\n   if(Number.isFinite(y))votes.set(y,(votes.get(y)||0)+1);"
    new_vote = "const y=Number.isFinite(p.baseline_hint)?p.baseline_hint:baselineVoteY(p,style);\n   if(Number.isFinite(y))votes.set(y,(votes.get(y)||0)+1);"
    if old_vote not in text:
        print("could not patch v27 baseline-hint voting", file=sys.stderr)
        return 2
    text = text.replace(old_vote, new_vote, 1)

    # Existing strict-y logic is useful for manual source shapes, but vertical
    # placement of propagated candidates is now decided by raster score, so make
    # the documentation unambiguous.
    text = text.replace("SAOL live-lärande pixelannotering v26", "SAOL live-lärande pixelannotering v27", 1)
    text = text.replace("corrected-v26.json", "corrected-v27.json")
    text = text.replace(
        "<b>Stil per annotation:</b>",
        "<b>Bläck först, stödlinje sedan:</b> varje inlärd glyph provas nu mot alla möjliga rasterlägen och väljs efter faktisk täckning av svart källbläck. En träff flyttas aldrig för att passa en redan uppskattad stödlinje; i stället ger träffen en baseline-röst från glyphens inlärda relativa läge. Manuell flytt av stödlinjen lämnar därför färgmarkeringen på originalbläcket. <b>Stil per annotation:</b>",
        1,
    )

    out.write_text(text, encoding="utf-8")
    print("v27: glyphs register to source ink first; implied baselines vote afterwards; baseline edits never move ink matches")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
