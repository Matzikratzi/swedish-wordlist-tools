from __future__ import annotations

import argparse
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
   // Tiny punctuation-like bodies must not dominate the normal text baseline.
   const w=Math.max(1,Number(s.width||1));
   const px=Math.max(1,Number(s.pixels||1));
   const weight=Math.min(3,Math.max(1,Math.round(Math.sqrt(px)/3)));
   counts.set(s.bottom,(counts.get(s.bottom)||0)+weight);
 }
 const ranked=[...counts.entries()].sort((a,b)=>b[1]-a[1]||a[0]-b[0]);
 if(!ranked.length)return [];
 const best=ranked[0][1];
 // Keep only levels with real raw-raster support. This intentionally excludes
 // absurd high levels such as y=5 in q-märka/qigong when bodies vote 11/14.
 let ys=ranked.filter(([,c])=>c>=Math.max(2,best*0.34)).map(([y])=>+y);
 // A descender level is commonly 3 px below the true baseline. If both are
 // present, preserve both for scoring; glyph evidence may then choose the upper.
 ys=[...new Set(ys)].sort((a,b)=>a-b);
 return ys;
}
function nearestAllowedBaselineV45(y,allowed){
 if(!allowed||!allowed.length)return y;
 let best=allowed[0],d=Math.abs(y-best);
 for(const a of allowed){const dd=Math.abs(y-a);if(dd<d){d=dd;best=a;}}
 return best;
}
function chooseRawBaselineV45(profile,current){
 const allowed=rawBaselineCandidatesV45(profile);
 if(!allowed.length)return {baseline:current,allowed};
 // Prefer the upper of two strongly supported levels separated by the usual
 // descender distance. Otherwise use the strongest/raw-seed-nearest level.
 const counts=new Map();for(const s of (profile.segs||[]))if(s.body)counts.set(s.bottom,(counts.get(s.bottom)||0)+1);
 let baseline=allowed[0],score=-Infinity;
 for(const y of allowed){
   let sc=10*(counts.get(y)||0);
   if(allowed.includes(y+3))sc+=7; // y likely baseline; y+3 likely descender bottom
   if(allowed.includes(y-3))sc-=2;
   if(Number.isFinite(current))sc-=0.1*Math.abs(y-current);
   if(sc>score){score=sc;baseline=y;}
 }
 return {baseline,allowed};
}
function clearAutoCandidatesV45(proposals){
 for(let i=proposals.length-1;i>=0;i--){
   const p=proposals[i];
   if(p.status!=='manual')proposals.splice(i,1);
 }
}
function regenerateAllAutoV45(card,proposals,state,INK){
 // A baseline change changes glyph geometry. Rebuild automatic candidates from
 // the persistent facit and live manual models rather than translating/reusing
 // the old candidate universe.
 clearAutoCandidatesV45(proposals);
 if(typeof facitExactHitsV38==='function')facitExactHitsV38(card,proposals,state,INK);
 if(typeof propagateAllManualAnnotations==='function')propagateAllManualAnnotations();
 // Re-run the normal scoring/partition chain on the newly generated universe.
 if(typeof rejectEmbeddedTinyV41==='function')rejectEmbeddedTinyV41(card,proposals,state,INK);
 if(typeof enforcePerfectFullGlyphDominanceV42==='function')enforcePerfectFullGlyphDominanceV42(card,proposals,state,INK);
 if(typeof finalExclusivePartitionV44==='function')finalExclusivePartitionV44(card,proposals,state,INK);
 state.regeneratedAtBaselineV45=state.baselineY;
 if(state.render)state.render();
}
'''
    text = text.replace(anchor, helpers + "\n" + anchor, 1)

    old = "const r=rawBaselineV41(INK,W,H);\n if(!r)return null;\n state.rawBaselineV41=r.baseline;state.rawBottomProfileV41=r.profile;\n if(state.baselineManual)return r;\n state.baselineY=r.baseline;card.dataset.baseline=String(r.baseline);"
    new = "const r=rawBaselineV41(INK,W,H);\n if(!r)return null;\n const rb=chooseRawBaselineV45(r.profile,r.baseline);\n state.rawBaselineV41=r.baseline;state.rawBottomProfileV41=r.profile;state.rawAllowedBaselinesV45=rb.allowed;\n if(state.baselineManual)return r;\n state.baselineY=rb.baseline;card.dataset.baseline=String(rb.baseline);"
    if old not in text:
        print("could not patch v45 raw baseline selection", file=sys.stderr)
        return 2
    text = text.replace(old, new, 1)

    # After automatic baseline choice, rebuild automatic candidates from scratch
    # at that geometry before any final partitioning.
    old2 = "if(typeof recomputeCandidateGeometry==='function')recomputeCandidateGeometry(card,proposals,state,INK);\n rejectEmbeddedTinyV41(card,proposals,state,INK);"
    new2 = "if(typeof recomputeCandidateGeometry==='function')recomputeCandidateGeometry(card,proposals,state,INK);\n regenerateAllAutoV45(card,proposals,state,INK);\n rejectEmbeddedTinyV41(card,proposals,state,INK);"
    if old2 not in text:
        print("could not patch v45 automatic regeneration", file=sys.stderr)
        return 2
    text = text.replace(old2, new2, 1)

    # Manual baseline buttons in the older editor eventually call the candidate
    # geometry recomputation path. Wrap it so any manual baseline change also
    # regenerates from facit rather than merely moving/reweighting stale matches.
    hook = "function regenerateAllAutoV45(card,proposals,state,INK){"
    wrapper = r'''
const recomputeCandidateGeometryV45Original=(typeof recomputeCandidateGeometry==='function')?recomputeCandidateGeometry:null;
if(recomputeCandidateGeometryV45Original){
 recomputeCandidateGeometry=function(card,proposals,state,INK){
   const before=state.baselineY;
   const out=recomputeCandidateGeometryV45Original(card,proposals,state,INK);
   if(state.baselineManual || state.baselineY!==before){
     setTimeout(()=>regenerateAllAutoV45(card,proposals,state,INK),0);
   }
   return out;
 };
}

'''
    text = text.replace(hook, wrapper + hook, 1)

    text = text.replace("SAOL live-lärande pixelannotering v44", "SAOL live-lärande pixelannotering v45", 1)
    text = text.replace("corrected-v44.json", "corrected-v45.json")
    text = text.replace(
        "<b>Exklusiv slutpartition v44:</b>",
        "<b>Rågeometriskt baslinjeintervall v45:</b> endast baslinjenivåer med starkt stöd från råglyphernas nedersta pixelnivåer får prövas automatiskt; nivåer långt ovanför kropparnas bottnar är förbjudna. Typisk nivå +3 behandlas som möjlig descenderbotten och den övre nivån föredras. Varje automatisk eller manuell baslinjeändring bygger dessutom om alla auto-kandidater från det permanenta glyphfacit vid den nya geometrin. <b>Exklusiv slutpartition v44:</b>",
        1,
    )

    args.out.write_text(text, encoding="utf-8")
    print("v45: raw raster constrains baseline hypotheses; every baseline change regenerates auto candidates from persistent facit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
