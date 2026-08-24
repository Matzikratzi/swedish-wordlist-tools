from __future__ import annotations

import sys
from pathlib import Path

from . import ocr_manual_pixel_candidate_editor_v23 as v23


def main() -> int:
    argv = sys.argv[1:]
    out: Path | None = None
    if "--out" in argv:
        i = argv.index("--out")
        if i + 1 < len(argv):
            out = Path(argv[i + 1])

    rc = v23.main()
    if rc or out is None or not out.exists():
        return rc

    text = out.read_text(encoding="utf-8")

    old = r'''const BASELINE_ANCHORS=new Set([..."abcdehiklmnorstuvwxåäö"]);
const STRICT_Y_LABELS=new Set(['.','·','-',',']);
function votedBaseline(proposals,current){
 const votes=new Map();
 for(const p of proposals){
   if(p.suppressed || !BASELINE_ANCHORS.has(p.label) || !p.pixels || !p.pixels.size)continue;
   let ymax=-Infinity;
   for(const k of p.pixels){const y=Number(k.split(',')[1]);if(y>ymax)ymax=y}
   if(Number.isFinite(ymax))votes.set(ymax,(votes.get(ymax)||0)+1);
 }
 let best=current,bestN=0;
 for(const [y,n] of votes){
   if(n>bestN || (n===bestN && Math.abs(y-current)<Math.abs(best-current))){best=y;bestN=n}
 }
 return {baseline:best,votes:bestN};
}'''

    new = r'''const BASELINE_ANCHORS=new Set([..."abcdehiklmnoprstuvwxåäö."]);
const STRICT_Y_LABELS=new Set(['.','·','-',',']);
function baselineVoteY(p,style){
 if(!p.pixels || !p.pixels.size)return null;
 const rows=new Map();
 for(const k of p.pixels){const y=Number(k.split(',')[1]);rows.set(y,(rows.get(y)||0)+1)}
 if(!rows.size)return null;
 const ys=[...rows.keys()].sort((a,b)=>a-b);
 if(style==='roman' && p.label==='p'){
   // Roman p descends below the baseline.  The baseline is at the bottom of
   // the bowl, not at the bottom of the stem.  The bowl rows are markedly
   // wider than the descender rows, so choose the lowest sufficiently wide row.
   const maxCount=Math.max(...rows.values());
   const threshold=Math.max(3,Math.ceil(maxCount*0.55));
   const bowl=ys.filter(y=>(rows.get(y)||0)>=threshold);
   if(bowl.length)return bowl[bowl.length-1];
 }
 return ys[ys.length-1];
}
function votedBaseline(proposals,current,style){
 const votes=new Map();
 for(const p of proposals){
   if(p.suppressed || !BASELINE_ANCHORS.has(p.label) || !p.pixels || !p.pixels.size)continue;
   const y=baselineVoteY(p,style);
   if(Number.isFinite(y))votes.set(y,(votes.get(y)||0)+1);
 }
 let best=current,bestN=0;
 for(const [y,n] of votes){
   if(n>bestN || (n===bestN && Math.abs(y-current)<Math.abs(best-current))){best=y;bestN=n}
 }
 return {baseline:best,votes:bestN};
}'''

    if old not in text:
        print("could not patch v24 baseline helper", file=sys.stderr)
        return 2
    text = text.replace(old, new, 1)

    old_call = "const bv=votedBaseline(proposals,state.baseline);"
    new_call = "const bv=votedBaseline(proposals,state.baseline,card.dataset.style);"
    if old_call not in text:
        print("could not patch v24 baseline vote call", file=sys.stderr)
        return 2
    text = text.replace(old_call, new_call)

    text = text.replace("SAOL live-lärande pixelannotering v23", "SAOL live-lärande pixelannotering v24", 1)
    text = text.replace("corrected-v23.json", "corrected-v24.json")
    text = text.replace(
        "<b>Glyph-röstad stödlinje:</b>",
        "<b>Roman-baslinje:</b> i roman pl. röstar l och punkt med sin nedersta bläckrad, medan p röstar med nederkanten på bågen och inte med descenderstammen. <b>Glyph-röstad stödlinje:</b>",
        1,
    )
    out.write_text(text, encoding="utf-8")
    print("v24: roman p votes from bowl bottom; l and period vote from bottom ink row")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
