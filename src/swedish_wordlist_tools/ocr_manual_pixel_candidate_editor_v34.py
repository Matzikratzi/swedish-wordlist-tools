from __future__ import annotations

import re
import sys
from pathlib import Path

from . import ocr_manual_pixel_candidate_editor_v33 as v33


def main() -> int:
    argv = sys.argv[1:]
    out: Path | None = None
    if "--out" in argv:
        i = argv.index("--out")
        if i + 1 < len(argv):
            out = Path(argv[i + 1])

    rc = v33.main()
    if rc or out is None or not out.exists():
        return rc

    text = out.read_text(encoding="utf-8")

    # v31 misunderstood "distance" as horizontal distance to lod markers.
    # Geometry is vertical distance to the support baseline.  Remove every lod
    # contribution from scoring; baseline_hint already carries the line implied
    # by the learned glyph's pixels_relative_to_baseline.
    text = text.replace(
        "const lodPenalty=Number.isFinite(+p.lod_distance_error)?4*Math.abs(+p.lod_distance_error):0;\n return (raw-lodPenalty)/total;",
        "const baselinePenalty=Number.isFinite(+p.baseline_distance_error)?4*Math.abs(+p.baseline_distance_error):0;\n return (raw-baselinePenalty)/total;",
        1,
    )

    # Row resolver needs the current support line in order to reject candidates
    # whose learned vertical geometry is wrong for this word.
    text = text.replace(
        "function resolveCandidateOverlaps(proposals,INK,W,H){",
        "function resolveCandidateOverlaps(proposals,INK,W,H,state){",
        1,
    )
    old_gate = "if(conflicts(occupiedManual,p) || crossesHardBlank(p)){p.suppressed=true;continue}\n   const rel=relativeGlyphScore(p);p.relative_score=rel;if(rel<MIN_RELATIVE_GLYPH_SCORE){p.suppressed=true;continue}"
    new_gate = "if(conflicts(occupiedManual,p) || crossesHardBlank(p)){p.suppressed=true;continue}\n   p.baseline_distance_error=Number.isFinite(+p.baseline_hint)?Math.abs((+p.baseline_hint)-state.baseline):0;\n   if(p.baseline_distance_error>=2){p.suppressed=true;continue}\n   const rel=relativeGlyphScore(p);p.relative_score=rel;if(rel<MIN_RELATIVE_GLYPH_SCORE){p.suppressed=true;continue}"
    if old_gate not in text:
        print("could not add v34 baseline quality gate", file=sys.stderr)
        return 2
    text = text.replace(old_gate, new_gate, 1)
    text = text.replace(
        "state.overlapSuppressed=resolveCandidateOverlaps(proposals,INK,W,H);",
        "state.overlapSuppressed=resolveCandidateOverlaps(proposals,INK,W,H,state);",
        1,
    )

    # Remove lod geometry from v33's row weight; exact/full-glyph weighting stays.
    old_weight_tail = " - (Number.isFinite(+p.lod_distance_error)?6*Math.abs(+p.lod_distance_error):0);"
    if old_weight_tail not in text:
        print("could not remove v34 lod row penalty", file=sys.stderr)
        return 2
    text = text.replace(old_weight_tail, " - (Number.isFinite(+p.baseline_distance_error)?6*Math.abs(+p.baseline_distance_error):0);", 1)

    # New live propagation: do not learn or compare any lod distance.  The
    # candidate's implied baseline is enough; one-row error is expensive and two
    # or more rows is impossible against the card's current support line.
    text = re.sub(
        r"\n const sourceTuple=allCards\.find\(t=>t\[0\]===sourceCard\);\n const sourceLodDx=sourceTuple\?nearestLodDistance\(sourceTuple\[1\],sourceProposal,true\):null;",
        "",
        text,
        count=1,
    )
    old_temp = "const temp={label:sourceProposal.label,style:sourceStyle,status:(missing||extra||context)?'propagated-context':'propagated-exact',pixels:abs,contacts:[],external_contacts:0,missing,extra,score,matched,total,propagated_from:sourceCard.dataset.subnr,baseline_hint:impliedBaseline,baseline_dy:impliedBaseline-state.baseline,lod_source_dx:sourceLodDx};\n       const targetLodDx=sourceLodDx===null?null:nearestLodDistance(proposals,temp,false);\n       if(sourceLodDx!==null && targetLodDx!==null){temp.lod_distance_error=Math.abs(targetLodDx-sourceLodDx);if(temp.lod_distance_error>=2)continue;}\n       const rel=(score-(Number.isFinite(temp.lod_distance_error)?4*temp.lod_distance_error:0))/Math.max(1,total);\n       if(rel<MIN_RELATIVE_GLYPH_SCORE)continue;temp.relative_score=rel;"
    new_temp = "const temp={label:sourceProposal.label,style:sourceStyle,status:(missing||extra||context)?'propagated-context':'propagated-exact',pixels:abs,contacts:[],external_contacts:0,missing,extra,score,matched,total,propagated_from:sourceCard.dataset.subnr,baseline_hint:impliedBaseline,baseline_dy:impliedBaseline-state.baseline};\n       temp.baseline_distance_error=Math.abs(impliedBaseline-state.baseline);if(temp.baseline_distance_error>=2)continue;\n       const rel=(score-4*temp.baseline_distance_error)/Math.max(1,total);\n       if(rel<MIN_RELATIVE_GLYPH_SCORE)continue;temp.relative_score=rel;"
    if old_temp not in text:
        print("could not replace v34 live lod geometry", file=sys.stderr)
        return 2
    text = text.replace(old_temp, new_temp, 1)

    # Same correction in the v32 per-word recompute path.
    text = text.replace("     const sourceLodDx=nearestLodDistance(sourceProposals,sourceProposal,true);\n", "", 1)
    old_recompute_temp = "const temp={label:sourceProposal.label,style:sourceStyle,status:(missing||extra)?'propagated-context':'propagated-exact',pixels:abs,contacts:[],external_contacts:0,missing,extra,score,matched,total,propagated_from:sourceCard.dataset.subnr,baseline_hint:y0+model.baselineOffset,lod_source_dx:sourceLodDx};\n         if(sourceLodDx!==null){\n           const targetLodDx=nearestLodDistance(targetProposals,temp,false);\n           if(targetLodDx!==null){temp.lod_distance_error=Math.abs(targetLodDx-sourceLodDx);if(temp.lod_distance_error>=2)continue;}\n         }\n         temp.relative_score=relativeGlyphScore(temp);"
    new_recompute_temp = "const impliedBaseline=y0+model.baselineOffset;\n         const temp={label:sourceProposal.label,style:sourceStyle,status:(missing||extra)?'propagated-context':'propagated-exact',pixels:abs,contacts:[],external_contacts:0,missing,extra,score,matched,total,propagated_from:sourceCard.dataset.subnr,baseline_hint:impliedBaseline,baseline_dy:impliedBaseline-targetState.baseline};\n         temp.baseline_distance_error=Math.abs(impliedBaseline-targetState.baseline);if(temp.baseline_distance_error>=2)continue;\n         temp.relative_score=relativeGlyphScore(temp);"
    if old_recompute_temp not in text:
        print("could not replace v34 recompute lod geometry", file=sys.stderr)
        return 2
    text = text.replace(old_recompute_temp, new_recompute_temp, 1)

    # When the human changes the support line, geometry scores have changed.
    # Keep manual ink exactly where it is, discard/rebuild automatics immediately.
    old_baseline = r'''b.onchange=()=>{
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
    new_baseline = r'''b.onchange=()=>{
 const newBaseline=Math.max(0,Math.min(H-1,+b.value));
 state.baseline=newBaseline;
 state.baselineManual=true;
 state.baselineVotes=0;
 card.dataset.baseline=String(newBaseline);
 b.value=newBaseline;
 // Manual source-ink pixels never move.  But every automatic candidate's
 // vertical geometry has changed, so rebuild this word immediately.
 const r=recomputeTargetCard(card,proposals,state,INK);
 state.baseline=newBaseline;
 state.baselineManual=true;
 state.baselineVotes=0;
 card.dataset.baseline=String(newBaseline);
 b.value=newBaseline;
 render();
 card.querySelector('.legend').textContent='Stödlinje ändrad · omräknat: '+r.added+' auto-kandidater';
};'''
    if old_baseline not in text:
        print("could not patch v34 baseline-triggered recompute", file=sys.stderr)
        return 2
    text = text.replace(old_baseline, new_baseline, 1)

    # Candidate chip/debug text and documentation.
    text = text.replace("+(Number.isFinite(p.lod_distance_error)?' · lod Δ'+p.lod_distance_error:'')", "+(Number.isFinite(p.baseline_distance_error)?' · stöd Δy'+p.baseline_distance_error:'')")
    text = text.replace(
        "Avståndet till närmaste manuellt inlärda lod/halvlod är stark geometri: 1 px fel kostar mycket och 2 px eller mer underkänns.",
        "Glyphens vertikala läge relativt stödlinjen är stark geometri: 1 px fel kostar mycket och 2 px eller mer underkänns. Flyttar du stödlinjen räknas ordet om direkt.",
    )
    text = text.replace("SAOL live-lärande pixelannotering v33", "SAOL live-lärande pixelannotering v34", 1)
    text = text.replace("corrected-v33.json", "corrected-v34.json")

    out.write_text(text, encoding="utf-8")
    print("v34: baseline-relative geometry replaces lod-distance scoring; baseline edits automatically recompute the word")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
