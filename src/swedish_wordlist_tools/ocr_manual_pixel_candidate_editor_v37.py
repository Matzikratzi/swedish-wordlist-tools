from __future__ import annotations

import re
import sys
from pathlib import Path

from . import ocr_manual_pixel_candidate_editor_v36 as v36


def main() -> int:
    argv = sys.argv[1:]
    out: Path | None = None
    if "--out" in argv:
        i = argv.index("--out")
        if i + 1 < len(argv):
            out = Path(argv[i + 1])

    rc = v36.main()
    if rc or out is None or not out.exists():
        return rc

    text = out.read_text(encoding="utf-8")

    # Keep enough vertical alternatives for the raster-derived baseline to
    # rescue candidates even when the historical initial baseline is several
    # rows wrong. Word crops are tiny, so +/-5 remains cheap.
    text = text.replace(
        "temp.baseline_distance_error=Math.abs(impliedBaseline-state.baseline);if(temp.baseline_distance_error>=4)continue;",
        "temp.baseline_distance_error=Math.abs(impliedBaseline-state.baseline);if(temp.baseline_distance_error>=6)continue;",
        1,
    )
    text = text.replace(
        "temp.baseline_distance_error=Math.abs(impliedBaseline-targetState.baseline);if(temp.baseline_distance_error>=4)continue;",
        "temp.baseline_distance_error=Math.abs(impliedBaseline-targetState.baseline);if(temp.baseline_distance_error>=6)continue;",
        1,
    )

    # Strengthen full-glyph exactness, but proportionally to glyph size. There
    # is still no fixed per-candidate windfall that can make four tiny fragments
    # beat one full n/l/etc.
    old = "const exactBonus=exact?0.45*p.pixels.size:0;"
    new = "const exactBonus=exact?1.35*p.pixels.size:0;"
    if old not in text:
        print("could not strengthen v37 exact glyph bonus", file=sys.stderr)
        return 2
    text = text.replace(old, new, 1)
    text = text.replace("const fragmentPenalty=3.5;", "const fragmentPenalty=5.0;", 1)

    # Replace v36's baseline optimiser with a raster-first seed followed by a
    # small search. The raster seed implements the requested heuristic:
    # 1) count black pixels per horizontal row;
    # 2) find the densest row;
    # 3) walk downward until density drops sharply to zero/almost-zero;
    # 4) use the last still-dense row before that drop as the baseline ink row.
    # Perfect glyphs (all model pixels on ink; no missing/extra) whose learned
    # baseline agrees with a tested row contribute a strong anchor bonus.
    opt_re = re.compile(
        r"function optimiseCardBaselineV36\(card,proposals,state,INK\)\{.*?\n\}",
        re.S,
    )
    replacement = r'''function rasterBaselineSeedV37(INK,W,H,fallback){
 const counts=[];let peak=-1,peakY=Math.max(0,Math.min(H-1,fallback));
 for(let y=0;y<H;y++){
   let n=0;for(let x=0;x<W;x++)if(INK[y]&&INK[y][x])n++;
   counts.push(n);if(n>peak){peak=n;peakY=y;}
 }
 if(peak<=0)return {y:peakY,counts,peakY,peak};
 // "Nearly zero" is deliberately relative to the row peak, with a small
 // absolute allowance for descenders / punctuation below the normal baseline.
 const dense=Math.max(3,Math.ceil(peak*0.42));
 const sparse=Math.max(1,Math.floor(peak*0.14));
 let candidate=peakY;
 for(let y=peakY;y<H;y++){
   const n=counts[y],next=(y+1<H?counts[y+1]:0);
   if(n>=dense)candidate=y;
   // A substantial row followed by near-empty ink is exactly the requested
   // "strax innan det glesar ut" signal.
   if(n>=dense && next<=sparse){candidate=y;break;}
   // If density has already collapsed after the peak, retain the last dense row.
   if(y>peakY && n<=sparse)break;
 }
 return {y:candidate,counts,peakY,peak,dense,sparse};
}
function exactAnchorScoreV37(proposals,y){
 let score=0,count=0,pixels=0;
 for(const p of proposals){
   if(p.status==='manual')continue;
   const exact=(+p.missing||0)===0 && (+p.extra||0)===0 &&
     (!Number.isFinite(+p.total) || (+p.matched||p.pixels.size)>=(+p.total||p.pixels.size));
   if(!exact || !Number.isFinite(+p.baseline_hint) || (+p.baseline_hint)!==y)continue;
   // A 100%-matched full glyph is strong baseline evidence. Reward by size so
   // one 34-pixel n outweighs several 5-pixel half-lod fragments.
   const sz=p.pixels?p.pixels.size:0;
   score+=2.2*sz;pixels+=sz;count++;
 }
 return {score,count,pixels};
}
function optimiseCardBaselineV36(card,proposals,state,INK){
 if(state.baselineManual)return {baseline:state.baseline,score:state.lastRowScore||0,tried:1,seed:state.baseline};
 const W=+card.dataset.w,H=+card.dataset.h;
 const oldInitial=state.baseline;
 const seedInfo=rasterBaselineSeedV37(INK,W,H,oldInitial);
 const seed=seedInfo.y;
 let bestY=seed,bestScore=-Infinity,tried=0,bestAnchors=null;
 // Search only around the raster-derived seed. This remains cheap: at most five
 // overlap/beam evaluations and no repeated raster glyph scan.
 const lo=Math.max(0,seed-2),hi=Math.min(H-1,seed+2);
 for(let y=lo;y<=hi;y++){
   state.baseline=y;
   resolveCandidateOverlaps(proposals,INK,W,H,state);
   const rowScore=Number.isFinite(state.lastRowScore)?state.lastRowScore:-Infinity;
   const anchors=exactAnchorScoreV37(proposals,y);
   const score=rowScore+anchors.score;
   tried++;
   if(score>bestScore+1e-9 ||
      (Math.abs(score-bestScore)<=1e-9 && Math.abs(y-seed)<Math.abs(bestY-seed))){
     bestScore=score;bestY=y;bestAnchors=anchors;
   }
 }
 state.baseline=bestY;
 state.baselineVotes=0;
 card.dataset.baseline=String(bestY);
 const b=card.querySelector('.baseline');if(b)b.value=bestY;
 resolveCandidateOverlaps(proposals,INK,W,H,state);
 state.autoBaselineInitial=oldInitial;
 state.autoBaselineRasterSeed=seed;
 state.autoBaselineScore=bestScore;
 state.autoBaselineTried=tried;
 state.autoBaselineExactAnchors=bestAnchors?bestAnchors.count:0;
 if(state.render)state.render();
 return {baseline:bestY,score:bestScore,tried,seed,anchors:bestAnchors,profile:seedInfo};
}'''
    if not opt_re.search(text):
        print("could not replace v36 optimiser with v37 raster baseline", file=sys.stderr)
        return 2
    text = opt_re.sub(replacement, text, count=1)

    # Recompute status: expose raster seed and exact anchors while tuning.
    old_status = "(ob?' · stödlinje '+ob.baseline+' ('+ob.tried+' lägen)':'')"
    new_status = "(ob?' · raster '+ob.seed+' → stödlinje '+ob.baseline+' ('+ob.tried+' lägen, '+((ob.anchors&&ob.anchors.count)||0)+' exakta ankare)':'')"
    if old_status in text:
        text = text.replace(old_status, new_status, 1)

    text = text.replace("SAOL live-lärande pixelannotering v36", "SAOL live-lärande pixelannotering v37", 1)
    text = text.replace("corrected-v36.json", "corrected-v37.json")
    text = text.replace(
        "<b>Stödlinje + rad tolkas tillsammans:</b>",
        "<b>Raster först:</b> stödlinjegissningen börjar med svartpixelantal per horisontell rad: från den tätaste raden går vi nedåt till den sista fortfarande täta raden innan bläcket faller kraftigt till nära noll. Kring den raden provas högst fem lägen. 100%-glypher — alla modellpixlar på svart, inga missing/extra — fungerar som starka ankare, med bonus proportionell mot glyphstorlek så ett helt fett n/l väger tyngre än flera små halvlodfragment. <b>Stödlinje + rad tolkas tillsammans:</b>",
        1,
    )

    out.write_text(text, encoding="utf-8")
    print("v37: raster-density baseline seed + exact full-glyph anchors; at most 5 baseline evaluations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
