from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import ocr_manual_pixel_candidate_editor_v43 as v43


def main() -> int:
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("matches")
    ap.add_argument("library")
    ap.add_argument("--out", type=Path, required=True)
    args, _ = ap.parse_known_args(sys.argv[1:])

    rc = v43.main()
    if rc or not args.out.exists():
        return rc

    text = args.out.read_text(encoding="utf-8")
    anchor = "function proposalIsPerfectV42(p){"
    if anchor not in text:
        print("could not find v44 helper anchor", file=sys.stderr)
        return 2

    helpers = r'''
function pixelKeyV44(p){
 if(!p||!p.pixels)return '';
 return [...p.pixels].sort((a,b)=>{
   const [ax,ay]=a.split(',').map(Number),[bx,by]=b.split(',').map(Number);
   return ax-bx||ay-by;
 }).join(';');
}
function weightV44(p){
 if(Number.isFinite(+p.beamWeightV43))return +p.beamWeightV43;
 const n=Math.max(1,p.pixels?p.pixels.size:0);
 const missing=Math.max(0,Number(p.missing||0));
 const extra=Math.max(0,Number(p.extra||0));
 const matched=Math.max(0,Number(p.matched ?? Math.max(0,n-missing)));
 const total=Math.max(1,Number(p.total ?? n));
 let rel=Number(p.relative_score);
 if(!Number.isFinite(rel))rel=Math.min(1,matched/total);
 rel=Math.max(0,Math.min(1,rel));
 const perfect=(missing===0&&extra===0&&matched===total&&rel>=0.999999);
 let value;
 if(perfect)value=n+1.55*Math.pow(n,1.6);
 else {
   const quality=Math.pow(rel,4);
   value=(n*quality)/(1+0.40*(missing+extra));
   if(rel>=0.97&&missing+extra<=2)value+=0.20*Math.pow(n,1.35)*quality;
 }
 if(p.facit)value*=1.10;
 if(p.status==='manual')value*=1000;
 p.beamWeightV43=value;p.beamQualityV43=rel;p.beamErrorsV43=missing+extra;
 return value;
}
function conflictsV44(occ,p){for(const k of p.pixels)if(occ.has(k))return true;return false;}
function spanV44(p){let lo=Infinity,hi=-Infinity;for(const k of p.pixels){const x=+k.split(',')[0];if(x<lo)lo=x;if(x>hi)hi=x;}return [lo,hi];}
function finalExclusivePartitionV44(card,proposals,state,INK){
 // This is the authoritative final auto-selection. Nothing after this function
 // is allowed to resurrect an automatic candidate.
 const manualOcc=new Set();
 for(const p of proposals)if(p.status==='manual'&&p.pixels)for(const k of p.pixels)manualOcc.add(k);

 // Start from a clean automatic state, but preserve hard vetoes.
 for(const p of proposals){
   if(p.status==='manual')continue;
   p.finalWinnerV44=false;
   const hard=!!(p.ignoreSuppressed||p.embeddedTiny||p.dominatedByFullGlyphV42);
   p.finalHardVetoV44=hard;
   p.suppressed=true;
 }

 // Deduplicate identical pixel sets before optimisation. Keep the strongest
 // explanation; ties prefer facit, then larger labels over punctuation-like
 // fragments, then earlier proposal order for determinism.
 const bestByPixels=new Map();
 const tinyLabels=new Set(['.','·','-',',','¤','|']);
 for(let i=0;i<proposals.length;i++){
   const p=proposals[i];
   if(p.status==='manual'||!p.pixels||!p.pixels.size||p.finalHardVetoV44)continue;
   if(conflictsV44(manualOcc,p))continue;
   const key=pixelKeyV44(p);if(!key)continue;
   const score=weightV44(p);
   const old=bestByPixels.get(key);
   const rank={p,i,score,facit:p.facit?1:0,tiny:tinyLabels.has(p.label)?1:0};
   if(!old || score>old.score+1e-9 ||
      (Math.abs(score-old.score)<=1e-9 && (rank.facit>old.facit ||
       (rank.facit===old.facit && rank.tiny<old.tiny)))) bestByPixels.set(key,rank);
 }
 const candidates=[...bestByPixels.values()];
 for(const c of candidates){const [lo,hi]=spanV44(c.p);c.lo=lo;c.hi=hi;}
 candidates.sort((a,b)=>a.lo-b.lo||a.hi-b.hi||b.score-a.score||a.i-b.i);

 // Beam-search an exclusive partition. V43's sharply quality-dependent score
 // is the objective; tiny uncovered source ink receives only a small tie-break,
 // so a large bad glyph cannot win by raw coverage alone.
 const BEAM=320;
 let states=[{value:0,covered:0,occ:new Set(),chosen:[]}];
 for(const c of candidates){
   const next=states.slice();
   for(const s of states){
     if(conflictsV44(s.occ,c.p))continue;
     const occ=new Set(s.occ);for(const k of c.p.pixels)occ.add(k);
     next.push({value:s.value+c.score,covered:s.covered+c.p.pixels.size,occ,chosen:s.chosen.concat(c.i)});
   }
   next.sort((a,b)=>(b.value+0.002*b.covered)-(a.value+0.002*a.covered));
   const dedup=[],seen=new Set();
   for(const s of next){
     const key=[...s.occ].sort().join(';');
     if(seen.has(key))continue;seen.add(key);dedup.push(s);
     if(dedup.length>=BEAM)break;
   }
   states=dedup;
 }
 const best=states[0]||{chosen:[],value:0,covered:0};
 const winners=new Set(best.chosen);
 for(let i=0;i<proposals.length;i++){
   const p=proposals[i];
   if(p.status==='manual')continue;
   if(winners.has(i)&&!p.finalHardVetoV44){p.suppressed=false;p.finalWinnerV44=true;}
   else p.suppressed=true;
 }
 state.finalPartitionV44={candidates:candidates.length,winners:winners.size,value:best.value,covered:best.covered,deduplicated:Math.max(0,proposals.filter(p=>p.status!=='manual'&&p.pixels&&p.pixels.size&&!p.finalHardVetoV44).length-candidates.length)};
 if(state.render)state.render();
 return state.finalPartitionV44;
}
'''
    text = text.replace(anchor, helpers + "\n" + anchor, 1)

    # v42's full-glyph dominance is currently the last automatic post-pass inside
    # applyRawBaselineV41. Put the authoritative v44 partition immediately after
    # it, so previous overlap/dominance passes become candidate preparation only.
    old = "enforcePerfectFullGlyphDominanceV42(card,proposals,state,INK);\n state.baselineVotes=(r.profile&&r.profile.votes)?r.profile.votes.size:0;"
    new = "enforcePerfectFullGlyphDominanceV42(card,proposals,state,INK);\n finalExclusivePartitionV44(card,proposals,state,INK);\n state.baselineVotes=(r.profile&&r.profile.votes)?r.profile.votes.size:0;"
    if old not in text:
        print("could not patch v44 automatic final partition", file=sys.stderr)
        return 2
    text = text.replace(old, new, 1)

    # Manual-baseline path bypasses applyRawBaselineV41, so install the same final
    # partition there as well.
    old2 = "else {rejectEmbeddedTinyV41(card,proposals,state,INK);enforcePerfectFullGlyphDominanceV42(card,proposals,state,INK);}"
    new2 = "else {rejectEmbeddedTinyV41(card,proposals,state,INK);enforcePerfectFullGlyphDominanceV42(card,proposals,state,INK);finalExclusivePartitionV44(card,proposals,state,INK);}"
    if old2 not in text:
        print("could not patch v44 manual-baseline path", file=sys.stderr)
        return 2
    text = text.replace(old2, new2)

    text = text.replace("SAOL live-lärande pixelannotering v43", "SAOL live-lärande pixelannotering v44", 1)
    text = text.replace("corrected-v43.json", "corrected-v44.json")
    text = text.replace(
        "<b>Kvalitetsviktning v43:</b>",
        "<b>Exklusiv slutpartition v44:</b> identiska pixelmängder dedupliceras och en sista auktoritativ beam-sökning väljer en enda icke-överlappande förklaring av rasterbläcket. Hårt underkända embedded/ignorerade fragment kan aldrig återaktiveras efter detta steg. V43:s kvalitetsvikt används direkt, så perfekta stora glyphar gynnas medan stora ofullständiga träffar inte får rå storleksbonus. <b>Kvalitetsviktning v43:</b>",
        1,
    )

    args.out.write_text(text, encoding="utf-8")
    print("v44: authoritative exclusive final raster partition; duplicate proposals collapsed; hard vetoes cannot resurrect")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
