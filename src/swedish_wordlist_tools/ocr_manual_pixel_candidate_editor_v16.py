from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from . import ocr_manual_pixel_candidate_editor_v15 as v15


def main() -> int:
    rc = v15.main()
    if rc:
        return rc

    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("matches")
    ap.add_argument("library")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--scale")
    ap.add_argument("--margin")
    ap.add_argument("--ink-threshold")
    ap.add_argument("--examples-per-char")
    args, _ = ap.parse_known_args(sys.argv[1:])

    text = args.out.read_text(encoding="utf-8")

    # A small exact template (for example a half-height separator) can fit inside
    # a larger glyph.  v6 only emitted exact-shape candidates, so a nearly exact
    # 'l' could be absent while the tiny separator survived.  Replace live
    # propagation by tolerant scoring: every learned manual shape is scanned at
    # all x positions and baseline-near y positions.  Candidate score rewards
    # explained ink and penalises missing/extra pixels.  This deliberately makes
    # a nearly complete l beat a perfect 5-pixel separator inside the same ink.
    fuzzy = r'''function propagateFinished(sourceCard,sourceProposal,sourceState){
 if(!sourceProposal || sourceProposal.status!=='manual' || !sourceProposal.label || !sourceProposal.pixels.size)return 0;
 const model=normManualShape(sourceProposal.pixels,sourceState.baseline);if(!model)return 0;
 let added=0;
 for(const tuple of allCards){
   const [card,proposals,state,INK]=tuple;
   if(card===sourceCard || card.dataset.style!==sourceCard.dataset.style)continue;
   const W=+card.dataset.w,H=+card.dataset.h;
   const idealY=state.baseline-model.baselineOffset;
   for(let dy=-1;dy<=1;dy++){
     const y0=idealY+dy;if(y0<0||y0+model.height>H)continue;
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
       const score=matched-2*missing-extra;
       if(score<=0)continue;
       if(proposals.some(p=>p.label===sourceProposal.label && samePixelSet(p.pixels,abs)))continue;
       const context=hasDetachedContextInk(INK,W,H,x0,y0,model.width,model.height,abs);
       proposals.push({label:sourceProposal.label,status:(missing||extra||context)?'propagated-context':'propagated-exact',pixels:abs,contacts:[],external_contacts:0,missing,extra,score,matched,total,propagated_from:sourceCard.dataset.subnr,baseline_dy:dy});
       added++;
     }
   }
   if(added)state._needsRender=true;
 }
 for(const [card,proposals,state] of allCards){if(card.dataset.style===sourceCard.dataset.style && state.render)state.render();state._needsRender=false}
 return added;
}'''
    pat = re.compile(r"function propagateFinished\(sourceCard,sourceProposal,sourceState\)\{.*?\n\}", re.S)
    if not pat.search(text):
        raise SystemExit("could not patch v16 fuzzy propagation")
    text = pat.sub(fuzzy, text, count=1)

    # Score first; fall back to explained pixel count and status for older
    # candidates that do not carry a score.
    old_sort = ".sort((a,b)=>b.pixels.size-a.pixels.size || candidatePriority(b)-candidatePriority(a));"
    new_sort = ".sort((a,b)=>(b.score??b.pixels.size)-(a.score??a.pixels.size) || b.pixels.size-a.pixels.size || candidatePriority(b)-candidatePriority(a));"
    if old_sort not in text:
        raise SystemExit("could not patch v16 candidate ranking")
    text = text.replace(old_sort, new_sort, 1)

    # Show score when available; useful for the l-vs-separator cases under review.
    text = text.replace(
        "+p.label+' · '+p.status+' · '+p.pixels.size+' px</span>'",
        "+p.label+' · '+p.status+' · '+p.pixels.size+' px'+(p.score!==undefined?' · poäng '+p.score:'')+'</span>'",
    )

    # Per-card progress marker.  It is deliberately separate from annotations:
    # it records review position, not glyph truth.
    text = text.replace(
        '<button class="clear" type="button">Rensa ordet</button>',
        '<button class="clear" type="button">Rensa ordet</button><button class="review-stop" type="button">Hit men inte längre</button>',
    )
    anchor = "const allCards=[];"
    if anchor not in text:
        raise SystemExit("could not install v16 progress state")
    text = text.replace(anchor, anchor + "\nlet reviewStop=null;", 1)

    export_anchor = "document.querySelector('#export').onclick=async()=>{"
    progress_js = r'''
document.querySelectorAll('.review-stop').forEach(btn=>btn.onclick=()=>{
 const card=btn.closest('.card');
 reviewStop={source_id:card.dataset.sourceId,expected_word:card.dataset.expected,headword:card.dataset.headword,style:card.dataset.style,page:Number(card.dataset.page),subnr:card.dataset.subnr,word_file:card.dataset.wordFile};
 document.querySelectorAll('.review-stop').forEach(b=>{b.textContent='Hit men inte längre';b.style.fontWeight=''});
 btn.textContent='HIT ✓';btn.style.fontWeight='800';
 const status=document.querySelector('#review-stop-status');if(status)status.textContent='Granskat t.o.m. '+card.dataset.expected+' (sida '+card.dataset.page+')';
});
'''
    if export_anchor not in text:
        raise SystemExit("could not install v16 progress handlers")
    text = text.replace(export_anchor, progress_js + "\n" + export_anchor, 1)

    text = text.replace(
        '<span id="server-save-status" style="font-size:12px;font-weight:600"></span>',
        '<span id="server-save-status" style="font-size:12px;font-weight:600"></span> <span id="review-stop-status" style="font-size:12px;font-weight:700"></span>',
        1,
    )

    # Add top-level review_progress to the exported atlas without changing the
    # existing word/annotation schema.
    out_pat = re.compile(r"const out=\{format:'saol-manual-pixel-atlas-corrected-v15',coordinate_system:([^,]+),words\};")
    m = out_pat.search(text)
    if not m:
        raise SystemExit("could not patch v16 export progress")
    text = out_pat.sub("const out={format:'saol-manual-pixel-atlas-corrected-v16',coordinate_system:\\1,review_progress:reviewStop,words};", text, count=1)

    text = text.replace("SAOL live-lärande pixelannotering v15", "SAOL live-lärande pixelannotering v16", 1)
    text = text.replace("corrected-v15.json", "corrected-v16.json")
    text = text.replace(
        "<p><b>Fet-skörd direkt:</b>",
        "<p><b>Poängmatchning:</b> inlärda glypher provas tolerant mot alla positioner nära baslinjen. Förklarade pixlar ger poäng; saknade och extra pixlar kostar, så en nästan komplett bokstav ska slå ett litet lodstreck som bara råkar passa inne i den. <b>Granskningsstopp:</b> knappen ‘Hit men inte längre’ sparar ord/sida i exportens review_progress. <b>Fet-skörd direkt:</b>",
        1,
    )

    args.out.write_text(text, encoding="utf-8")
    print("v16: fuzzy coverage scoring + persisted 'Hit men inte längre' review marker")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
