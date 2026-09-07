from __future__ import annotations

import re
import sys
from pathlib import Path

from . import ocr_manual_pixel_candidate_editor_v29 as v29


def main() -> int:
    argv = sys.argv[1:]
    out: Path | None = None
    if "--out" in argv:
        i = argv.index("--out")
        if i + 1 < len(argv):
            out = Path(argv[i + 1])

    rc = v29.main()
    if rc or out is None or not out.exists():
        return rc

    text = out.read_text(encoding="utf-8")

    # Replace v7's largest-first greedy allocator.  That strategy lets one broad
    # accidental glyph (notably m) consume ink that is better explained by two
    # neighbouring glyphs (e.g. n+k).  The new resolver performs a bounded beam
    # search over the whole word and maximises total explained/quality-weighted
    # ink while still enforcing one-use-per-pixel.
    resolver_re = re.compile(
        r"function resolveCandidateOverlaps\(proposals\)\{.*?\n\}",
        re.S,
    )
    new_resolver = r'''function resolveCandidateOverlaps(proposals,INK,W,H){
 for(const p of proposals)p.suppressed=false;
 const occupiedManual=new Set();
 for(const p of proposals)if(p.status==='manual')for(const k of p.pixels)occupiedManual.add(k);

 function span(p){
   let lo=Infinity,hi=-Infinity;
   for(const k of p.pixels){const x=+k.split(',')[0];if(x<lo)lo=x;if(x>hi)hi=x}
   return [lo,hi];
 }
 function crossesHardBlank(p){
   const [lo,hi]=span(p);if(!Number.isFinite(lo)||hi<=lo+1)return false;
   // A completely white source column is a genuine inter-glyph/word gap in
   // these digitally typeset rasters.  A single-glyph candidate may not bridge it.
   for(let x=lo+1;x<hi;x++){
     let any=false;
     for(let y=0;y<H;y++)if(INK[y]&&INK[y][x]){any=true;break}
     if(!any)return true;
   }
   return false;
 }
 function conflicts(set,p){for(const k of p.pixels)if(set.has(k))return true;return false}
 function weight(p){
   const q=Number.isFinite(+p.score)?+p.score:p.pixels.size;
   const quality=Math.max(0.25,q);
   // Primary objective: explain real ink.  Quality score breaks near ties and
   // penalises candidates with missing/extra pixels from v27.
   return p.pixels.size + 0.45*quality;
 }

 const automatic=[];
 for(let i=0;i<proposals.length;i++){
   const p=proposals[i];
   if(p.status==='manual')continue;
   if(!p.pixels || !p.pixels.size){p.suppressed=true;continue}
   if(conflicts(occupiedManual,p) || crossesHardBlank(p)){p.suppressed=true;continue}
   const [lo,hi]=span(p);
   automatic.push({p,i,lo,hi,w:weight(p)});
 }
 // Left-to-right ordering helps the beam retain genuinely different parses.
 automatic.sort((a,b)=>a.lo-b.lo || a.hi-b.hi || b.w-a.w);

 const BEAM=192;
 let states=[{value:0,covered:0,occ:new Set(),chosen:[]}];
 for(const c of automatic){
   const next=states.slice(); // skip candidate
   for(const s of states){
     if(conflicts(s.occ,c.p))continue;
     const occ=new Set(s.occ);for(const k of c.p.pixels)occ.add(k);
     next.push({value:s.value+c.w,covered:s.covered+c.p.pixels.size,occ,chosen:s.chosen.concat(c.i)});
   }
   // Keep a diverse bounded frontier.  A tiny coverage tie-break favours the
   // parse that explains more source ink rather than one oversized local glyph.
   next.sort((a,b)=>(b.value+0.02*b.covered)-(a.value+0.02*a.covered));
   const dedup=[];const seen=new Set();
   for(const s of next){
     const key=[...s.occ].sort().join(';');
     if(seen.has(key))continue;seen.add(key);dedup.push(s);
     if(dedup.length>=BEAM)break;
   }
   states=dedup;
 }
 const best=states[0]||{chosen:[]};
 const winners=new Set(best.chosen);
 let suppressed=0;
 for(let i=0;i<proposals.length;i++){
   const p=proposals[i];if(p.status==='manual')continue;
   if(p.suppressed || !winners.has(i)){if(!p.suppressed)p.suppressed=true;suppressed++}
 }
 return suppressed;
}'''
    if not resolver_re.search(text):
        print("could not replace v30 overlap resolver", file=sys.stderr)
        return 2
    text = resolver_re.sub(new_resolver, text, count=1)

    old_call = "state.overlapSuppressed=resolveCandidateOverlaps(proposals);"
    new_call = "state.overlapSuppressed=resolveCandidateOverlaps(proposals,INK,W,H);"
    if old_call not in text:
        print("could not patch v30 resolver call", file=sys.stderr)
        return 2
    text = text.replace(old_call, new_call, 1)

    text = text.replace("SAOL live-lärande pixelannotering v29", "SAOL live-lärande pixelannotering v30", 1)
    text = text.replace("corrected-v29.json", "corrected-v30.json")
    text = text.replace(
        "<b>En pixel, en match:</b>",
        "<b>Helradsoptimering:</b> auto-kandidater väljs inte längre girigt med största glyph först. Editorn söker en kombination som maximerar hela ordets sammanlagda förklarade bläck/poäng. Helt vita rasterkolumner är hårda gränser som en enskild glyph inte får korsa. <b>En pixel, en match:</b>",
        1,
    )
    out.write_text(text, encoding="utf-8")
    print("v30: whole-row beam optimisation replaces largest-first greedy overlap resolution; hard blank columns split glyph candidates")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
