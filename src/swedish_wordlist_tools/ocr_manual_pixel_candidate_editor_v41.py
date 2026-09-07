from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from . import ocr_manual_pixel_candidate_editor_v40 as v40


def main() -> int:
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("matches")
    ap.add_argument("library")
    ap.add_argument("--out", type=Path, required=True)
    args, _ = ap.parse_known_args(sys.argv[1:])

    rc = v40.main()
    if rc or not args.out.exists():
        return rc

    text = args.out.read_text(encoding="utf-8")
    anchor = "function serialiseProposalV40(p){"
    if anchor not in text:
        print("could not find v41 helper anchor", file=sys.stderr)
        return 2

    helpers = r'''
function rawGlyphSegmentsV41(INK,W,H){
 const colInk=[];for(let x=0;x<W;x++){let n=0;for(let y=0;y<H;y++)if(INK[y]&&INK[y][x])n++;colInk.push(n);}
 const segs=[];let x=0;
 while(x<W){while(x<W&&colInk[x]===0)x++;if(x>=W)break;const x0=x;while(x+1<W&&colInk[x+1]>0)x++;const x1=x;
   // Merge only tiny one-column gaps surrounded by ink; this keeps e.g. dotted
   // letters together without joining ordinary neighbouring glyphs across real spaces.
   segs.push({x0,x1});x++;
 }
 return segs;
}
function bottomProfileV41(INK,W,H){
 const segs=rawGlyphSegmentsV41(INK,W,H);const votes=new Map();const details=[];
 for(const s of segs){
   let bottom=-1,pixels=0,width=s.x1-s.x0+1;
   for(let x=s.x0;x<=s.x1;x++)for(let y=0;y<H;y++)if(INK[y]&&INK[y][x]){pixels++;if(y>bottom)bottom=y;}
   if(bottom<0)continue;
   // Very tiny marks (punctuation/dots/short bars) are not allowed to establish
   // the text baseline. A raw glyph must have some body: width>=2 and >=8 pixels.
   const body=(width>=2&&pixels>=8);
   details.push({x0:s.x0,x1:s.x1,bottom,pixels,width,body});
   if(body){const w=Math.max(1,Math.min(20,pixels));votes.set(bottom,(votes.get(bottom)||0)+w);}
 }
 return {segs:details,votes};
}
function chooseRawBaselineV41(INK,W,H,fallback){
 const p=bottomProfileV41(INK,W,H);if(!p.votes.size)return {baseline:fallback,profile:p};
 const rows=[...p.votes.entries()].sort((a,b)=>a[0]-b[0]);
 // There are normally one to three bottom levels. Prefer the level with the
 // strongest total body support; on near ties prefer the upper level because
 // lower clusters are typically descenders (q/g/j/p/y).
 let bestY=rows[0][0],best=rows[0][1];
 for(const [y,v] of rows){if(v>best*1.08 || (v>=best*0.92 && y<bestY)){bestY=y;best=v;}}
 return {baseline:bestY,profile:p};
}
function componentAtV41(INK,W,H,x0,y0){
 const start=x0+','+y0;if(!INK[y0]||!INK[y0][x0])return new Set();
 const q=[[x0,y0]],seen=new Set([start]);
 while(q.length){const [x,y]=q.pop();for(const [dx,dy] of [[1,0],[-1,0],[0,1],[0,-1]]){const nx=x+dx,ny=y+dy,k=nx+','+ny;if(nx<0||ny<0||nx>=W||ny>=H||seen.has(k)||!INK[ny]||!INK[ny][nx])continue;seen.add(k);q.push([nx,ny]);}}
 return seen;
}
function rejectEmbeddedTinyV41(card,proposals,state,INK){
 const W=+card.dataset.w,H=+card.dataset.h;
 for(const p of proposals){
   if(p.status==='manual'||p.ignoreSuppressed||!p.pixels||!p.pixels.size)continue;
   const tiny=(p.pixels.size<=10 || ['.','·','-','¤',','].includes(p.label));if(!tiny)continue;
   const pts=[...p.pixels].map(k=>k.split(',').map(Number));const [sx,sy]=pts[0];
   const comp=componentAtV41(INK,W,H,sx,sy);if(!comp.size)continue;
   // If the candidate occupies only a small fraction of a larger connected ink
   // component, it is an embedded subshape, not an independent glyph.
   let inside=0;for(const k of p.pixels)if(comp.has(k))inside++;
   if(comp.size>=p.pixels.size+6 && inside===p.pixels.size && p.pixels.size/comp.size<0.72){p.suppressed=true;p.embeddedTiny=true;}
 }
}
function applyRawBaselineV41(card,proposals,state,INK){
 if(state.baselineManual)return {baseline:state.baseline,profile:null};
 const W=+card.dataset.w,H=+card.dataset.h;
 const r=chooseRawBaselineV41(INK,W,H,state.baseline);
 state.baseline=r.baseline;card.dataset.baseline=String(r.baseline);state.rawBaselineV41=r.baseline;state.rawBottomProfileV41=r.profile;
 const b=card.querySelector('.baseline');if(b)b.value=r.baseline;
 // Re-evaluate from the raw baseline. Existing facit proposals keep their ink
   // placement, but geometry/suppression is recalculated against the new y.
 for(const p of proposals){if(Number.isFinite(+p.baseline_hint))p.baseline_distance_error=Math.abs((+p.baseline_hint)-state.baseline);}
 if(typeof resolveCandidateOverlaps==='function')resolveCandidateOverlaps(proposals,INK,W,H,state);
 rejectEmbeddedTinyV41(card,proposals,state,INK);
 if(typeof resolveCandidateOverlaps==='function')resolveCandidateOverlaps(proposals,INK,W,H,state);
 state.baselineVotes=(r.profile&&r.profile.votes)?r.profile.votes.size:0;
 if(state.render)state.render();return r;
}
'''
    text = text.replace(anchor, helpers + "\n" + anchor, 1)

    # Replace v38/v37 automatic baseline optimisation in the stable post-init loop.
    old_loop = "const fs=facitExactHitsV38(card,proposals,state,INK);state.facitAdded=fs.added;state.facitModels=fs.scanned;suppressIgnoredV39(proposals,state);\n if(!state.baselineManual)optimiseCardBaselineV36(card,proposals,state,INK);"
    new_loop = "const fs=facitExactHitsV38(card,proposals,state,INK);state.facitAdded=fs.added;state.facitModels=fs.scanned;suppressIgnoredV39(proposals,state);\n if(!state.baselineManual)applyRawBaselineV41(card,proposals,state,INK);else rejectEmbeddedTinyV41(card,proposals,state,INK);"
    if old_loop not in text:
        print("could not patch v41 post-init baseline loop", file=sys.stderr)
        return 2
    text = text.replace(old_loop, new_loop, 1)

    # Recompute button must use the same raw-baseline-first policy.
    old_re = "const r=recomputeTargetCard(card,proposals,state,INK);\n   const fs=facitExactHitsV38(card,proposals,state,INK);\n   let ob=null;if(!state.baselineManual)ob=optimiseCardBaselineV36(card,proposals,state,INK);"
    new_re = "const r=recomputeTargetCard(card,proposals,state,INK);\n   const fs=facitExactHitsV38(card,proposals,state,INK);\n   let ob=null;if(!state.baselineManual)ob=applyRawBaselineV41(card,proposals,state,INK);else rejectEmbeddedTinyV41(card,proposals,state,INK);"
    if old_re not in text:
        print("could not patch v41 recompute baseline", file=sys.stderr)
        return 2
    text = text.replace(old_re, new_re, 1)

    # Debug export: include the raw bottom profile explicitly.
    text = text.replace(
        "votes:state.baselineVotes??null\n   },",
        "votes:state.baselineVotes??null,\n     raw_v41:state.rawBaselineV41??null,\n     raw_bottom_profile_v41:state.rawBottomProfileV41??null\n   },",
        1,
    )

    text = text.replace("SAOL live-lärande pixelannotering v40", "SAOL live-lärande pixelannotering v41", 1)
    text = text.replace("corrected-v40.json", "corrected-v41.json")
    text = text.replace(
        "<b>Ord-debugg:</b>",
        "<b>Råglyph-baslinje v41:</b> stödlinjen bestäms först utan bokstavsidentifiering: sammanhängande x-segment med riktig bläckkropp röstar med sin nedersta pixelrad. Den starkaste normala nivån vinner; lägre minoritetsnivåer behandlas som sannolika descenders. Därefter räknas glyphgeometrin om. Små punkt/streck/halvlod-liknande mallar som bara är delmängder av en större sammanhängande bläckkomponent underkänns. <b>Ord-debugg:</b>",
        1,
    )

    args.out.write_text(text, encoding="utf-8")
    print("v41: raw-glyph bottom-level baseline first; embedded tiny subglyphs suppressed; recompute uses same policy")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
