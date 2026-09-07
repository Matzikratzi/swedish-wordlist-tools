from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from . import ocr_manual_pixel_candidate_editor_v44 as v44


def main() -> int:
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("matches")
    ap.add_argument("library")
    ap.add_argument("--out", type=Path, required=True)
    args, _ = ap.parse_known_args(sys.argv[1:])

    rc = v44.main()
    if rc or not args.out.exists():
        return rc

    text = args.out.read_text(encoding="utf-8")
    anchor = "function rawGlyphSegmentsV41(INK,W,H){"
    if anchor not in text:
        print("could not find v45 helper anchor", file=sys.stderr)
        return 2

    helpers = r'''
function rawBaselineCandidatesV45(profile){
 const segs=(profile&&profile.segs)||[];
 const counts=new Map();
 for(const s of segs){
   if(!s.body)continue;
   const px=Math.max(1,Number(s.pixels||1));
   const weight=Math.min(4,Math.max(1,Math.round(Math.sqrt(px)/2.5)));
   counts.set(Number(s.bottom),(counts.get(Number(s.bottom))||0)+weight);
 }
 const ranked=[...counts.entries()].sort((a,b)=>b[1]-a[1]||a[0]-b[0]);
 if(!ranked.length)return [];
 const best=ranked[0][1];
 let ys=ranked.filter(([,c])=>c>=Math.max(2,best*0.34)).map(([y])=>+y);
 return [...new Set(ys)].sort((a,b)=>a-b);
}
function chooseRawBaselineV45(profile,current){
 const allowed=rawBaselineCandidatesV45(profile);
 if(!allowed.length)return {baseline:current,allowed};
 const counts=new Map();
 for(const s of (profile.segs||[]))if(s.body)counts.set(Number(s.bottom),(counts.get(Number(s.bottom))||0)+1);
 let baseline=allowed[0],score=-Infinity;
 for(const y of allowed){
   let sc=10*(counts.get(y)||0);
   if(allowed.includes(y+3))sc+=8; // lower level is likely descenders
   if(allowed.includes(y-3))sc-=3;
   if(Number.isFinite(current))sc-=0.05*Math.abs(y-current);
   if(sc>score){score=sc;baseline=y;}
 }
 return {baseline,allowed};
}
function clearAutoCandidatesV45(proposals){
 for(let i=proposals.length-1;i>=0;i--)if(proposals[i].status!=='manual')proposals.splice(i,1);
}
function regenerateAllAutoV45(card,proposals,state,INK){
 clearAutoCandidatesV45(proposals);
 if(typeof facitExactHitsV38==='function')facitExactHitsV38(card,proposals,state,INK);
 if(typeof propagateAllManualAnnotations==='function')propagateAllManualAnnotations();
 if(typeof rejectEmbeddedTinyV41==='function')rejectEmbeddedTinyV41(card,proposals,state,INK);
 if(typeof enforcePerfectFullGlyphDominanceV42==='function')enforcePerfectFullGlyphDominanceV42(card,proposals,state,INK);
 if(typeof finalExclusivePartitionV44==='function')finalExclusivePartitionV44(card,proposals,state,INK);
 state.regeneratedAtBaselineV45=state.baseline;
 if(state.render)state.render();
}
'''
    text = text.replace(anchor, helpers + "\n" + anchor, 1)

    # Replace the complete v41 baseline chooser with a v45 chooser that only
    # returns raw-raster-supported levels. This is robust to later wrappers
    # around applyRawBaselineV41.
    chooser_re = re.compile(
        r"function chooseRawBaselineV41\(INK,W,H,fallback\)\{.*?\n\}",
        re.S,
    )
    new_chooser = r'''function chooseRawBaselineV41(INK,W,H,fallback){
 const p=bottomProfileV41(INK,W,H);
 const rb=chooseRawBaselineV45(p,fallback);
 return {baseline:rb.baseline,profile:p,allowedV45:rb.allowed};
}'''
    if not chooser_re.search(text):
        print("could not patch v45 raw baseline chooser", file=sys.stderr)
        return 2
    text = chooser_re.sub(new_chooser, text, count=1)

    # Patch applyRawBaselineV41 itself at stable statements that are still
    # present after v42-v44. Record allowed levels, and regenerate the automatic
    # candidate universe after committing the baseline.
    old = "state.baseline=r.baseline;card.dataset.baseline=String(r.baseline);state.rawBaselineV41=r.baseline;state.rawBottomProfileV41=r.profile;"
    new = "state.baseline=r.baseline;card.dataset.baseline=String(r.baseline);state.rawBaselineV41=r.baseline;state.rawBottomProfileV41=r.profile;state.rawAllowedBaselinesV45=r.allowedV45||rawBaselineCandidatesV45(r.profile);"
    if old not in text:
        print("could not patch v45 baseline assignment", file=sys.stderr)
        return 2
    text = text.replace(old, new, 1)

    old2 = "for(const p of proposals){if(Number.isFinite(+p.baseline_hint))p.baseline_distance_error=Math.abs((+p.baseline_hint)-state.baseline);}"
    new2 = "regenerateAllAutoV45(card,proposals,state,INK);\n for(const p of proposals){if(Number.isFinite(+p.baseline_hint))p.baseline_distance_error=Math.abs((+p.baseline_hint)-state.baseline);}"
    if old2 not in text:
        print("could not patch v45 automatic regeneration", file=sys.stderr)
        return 2
    text = text.replace(old2, new2, 1)

    # Manual baseline changes eventually flow through recomputeTargetCard in the
    # editor. Wrap it once: if the baseline is manual, rebuild all automatic
    # proposals from the persistent facit after the ordinary recomputation.
    hook = "function regenerateAllAutoV45(card,proposals,state,INK){"
    wrapper = r'''
const recomputeTargetCardV45Original=(typeof recomputeTargetCard==='function')?recomputeTargetCard:null;
if(recomputeTargetCardV45Original){
 recomputeTargetCard=function(card,proposals,state,INK){
   const out=recomputeTargetCardV45Original(card,proposals,state,INK);
   if(state.baselineManual)setTimeout(()=>regenerateAllAutoV45(card,proposals,state,INK),0);
   return out;
 };
}

'''
    text = text.replace(hook, wrapper + hook, 1)

    text = text.replace("SAOL live-lärande pixelannotering v44", "SAOL live-lärande pixelannotering v45", 1)
    text = text.replace("corrected-v44.json", "corrected-v45.json")
    text = text.replace(
        "<b>Exklusiv slutpartition v44:</b>",
        "<b>Rågeometriskt baslinjeintervall v45:</b> endast nivåer som råglyphernas nedersta pixlar faktiskt stöder får väljas automatiskt. En nivå tre pixlar under en annan stark nivå behandlas som sannolik descenderbotten, så den övre nivån gynnas. När baslinjen ändras byggs de automatiska kandidaterna om från det permanenta glyphfacit i stället för att gamla träffar bara flyttas eller omvärderas. <b>Exklusiv slutpartition v44:</b>",
        1,
    )

    args.out.write_text(text, encoding="utf-8")
    print("v45: raw raster constrains baseline hypotheses; baseline changes regenerate auto candidates from persistent facit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
