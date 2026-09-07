from __future__ import annotations

import re
import sys
from pathlib import Path

from . import ocr_manual_pixel_candidate_editor_v31 as v31


def main() -> int:
    argv = sys.argv[1:]
    out: Path | None = None
    if "--out" in argv:
        i = argv.index("--out")
        if i + 1 < len(argv):
            out = Path(argv[i + 1])

    rc = v31.main()
    if rc or out is None or not out.exists():
        return rc

    text = out.read_text(encoding="utf-8")

    # v15 assumed /api/save-atlas always returned JSON.  Plain python
    # http.server quite correctly returns an HTML 404, which produced the noisy
    # JSON.parse SyntaxError even though the local download still succeeded.
    old_save = r'''const response=await fetch('/api/save-atlas',{method:'POST',headers:{'Content-Type':'application/json'},body:exportText});
   const result=await response.json();
   if(!response.ok || !result.ok)throw new Error(result.error||('HTTP '+response.status));
   saveMessage='Server: '+result.version_file+' · '+result.word_count+' ord';'''
    new_save = r'''const response=await fetch('/api/save-atlas',{method:'POST',headers:{'Content-Type':'application/json'},body:exportText});
   const body=await response.text();
   if(!response.ok){
     if(response.status===404){saveMessage='Serversparning saknas på denna webbserver · lokal fil laddas ned';}
     else{throw new Error('HTTP '+response.status+(body?' · '+body.slice(0,120):''));}
   }else{
     let result=null;
     try{result=body?JSON.parse(body):null}catch(_err){throw new Error('servern svarade inte med JSON');}
     if(!result || !result.ok)throw new Error((result&&result.error)||'okänt serversvar');
     saveMessage='Server: '+result.version_file+' · '+result.word_count+' ord';
   }'''
    if old_save not in text:
        print("could not patch v32 robust server-save response", file=sys.stderr)
        return 2
    text = text.replace(old_save, new_save, 1)

    # Add a button next to the other per-card cleanup controls.
    clear_label_btn = '<button class="clear-label" type="button">Rensa bokstav</button>'
    recompute_btn = clear_label_btn + '<button class="recompute-word" type="button">Räkna om ordet</button>'
    if clear_label_btn not in text:
        print("could not add v32 recompute button", file=sys.stderr)
        return 2
    text = text.replace(clear_label_btn, recompute_btn)

    # Targeted matcher: same ink-first scoring principle as v27/v31, but only for
    # one requested card.  This deliberately does NOT mutate other cards.
    anchor = "document.querySelectorAll('.card').forEach(card=>{"
    helper = r'''
function recomputeTargetCard(targetCard,targetProposals,targetState,targetINK){
 const W=+targetCard.dataset.w,H=+targetCard.dataset.h;
 // Manual annotations are user truth and survive recomputation. Everything
 // automatic is disposable and rebuilt from the current learned atlas.
 for(let i=targetProposals.length-1;i>=0;i--)if(targetProposals[i].status!=='manual')targetProposals.splice(i,1);
 let added=0,tried=0,rejectedQuality=0,rejectedGap=0;
 for(const [sourceCard,sourceProposals,sourceState] of allCards){
   for(const sourceProposal of sourceProposals){
     if(sourceProposal.status!=='manual' || !sourceProposal.label || !sourceProposal.pixels || !sourceProposal.pixels.size)continue;
     // A manual annotation already on this card is still a useful model, but do
     // not rediscover the exact same pixel set as an automatic duplicate.
     const sourceStyle=proposalStyle(sourceProposal,sourceCard);
     const model=normManualShape(sourceProposal.pixels,sourceState.baseline);if(!model)continue;
     const sourceLodDx=nearestLodDistance(sourceProposals,sourceProposal,true);
     for(let y0=0;y0+model.height<=H;y0++){
       for(let x0=0;x0+model.width<=W;x0++){
         tried++;
         const abs=new Set();let matched=0,missing=0,extra=0;
         const expected=new Set(model.shape.map(([dx,dy])=>(x0+dx)+','+(y0+dy)));
         for(const [dx,dy] of model.shape){
           const x=x0+dx,y=y0+dy;
           if(targetINK[y]&&targetINK[y][x]){matched++;abs.add(x+','+y)}else missing++;
         }
         const total=model.shape.length;
         if(matched<3)continue;
         for(let y=y0;y<y0+model.height;y++)for(let x=x0;x<x0+model.width;x++){
           if(targetINK[y]&&targetINK[y][x]&&!expected.has(x+','+y))extra++;
         }
         const missRatio=missing/Math.max(1,total),extraRatio=extra/Math.max(1,total);
         if(missRatio>.25 || extraRatio>.35)continue;
         const score=matched-2*missing-extra;if(score<=0)continue;
         const temp={label:sourceProposal.label,style:sourceStyle,status:(missing||extra)?'propagated-context':'propagated-exact',pixels:abs,contacts:[],external_contacts:0,missing,extra,score,matched,total,propagated_from:sourceCard.dataset.subnr,baseline_hint:y0+model.baselineOffset,lod_source_dx:sourceLodDx};
         if(sourceLodDx!==null){
           const targetLodDx=nearestLodDistance(targetProposals,temp,false);
           if(targetLodDx!==null){temp.lod_distance_error=Math.abs(targetLodDx-sourceLodDx);if(temp.lod_distance_error>=2)continue;}
         }
         temp.relative_score=relativeGlyphScore(temp);
         if(temp.relative_score<MIN_RELATIVE_GLYPH_SCORE){rejectedQuality++;continue;}
         // Respect digitally clean hard gaps before adding the candidate. The
         // row resolver repeats this guard, but rejecting here avoids clutter.
         let lo=Infinity,hi=-Infinity;
         for(const k of temp.pixels){const x=+k.split(',')[0];lo=Math.min(lo,x);hi=Math.max(hi,x)}
         let crosses=false;
         for(let x=lo+1;x<hi && !crosses;x++){
           let any=false;for(let y=0;y<H;y++)if(targetINK[y]&&targetINK[y][x]){any=true;break}
           if(!any)crosses=true;
         }
         if(crosses){rejectedGap++;continue;}
         if(targetProposals.some(p=>p.label===temp.label && proposalStyle(p,targetCard)===sourceStyle && samePixelSet(p.pixels,abs)))continue;
         targetProposals.push(temp);added++;
       }
     }
   }
 }
 targetState.baselineManual=false;
 targetState.baselineVotes=0;
 if(targetState.render)targetState.render();
 return {added,tried,rejectedQuality,rejectedGap};
}
'''
    if anchor not in text:
        print("could not add v32 targeted recompute helper", file=sys.stderr)
        return 2
    text = text.replace(anchor, helper + "\n" + anchor, 1)

    # Install card-local button handler after v31's clear-label handler.
    marker = "card.querySelector('.clear-label').onclick=()=>{"
    pos = text.find(marker)
    if pos < 0:
        print("could not find v31 clear-label handler for v32", file=sys.stderr)
        return 2
    # Insert immediately before the card image setup, which is stable in the
    # generated editor and avoids trying to regex-match nested JS braces.
    image_anchor = " const img=card.querySelector('.src');"
    handler = r'''
 card.querySelector('.recompute-word').onclick=()=>{
   const r=recomputeTargetCard(card,proposals,state,INK);
   card.querySelector('.legend').textContent='Omräknat: '+r.added+' auto-kandidater · '+r.rejectedQuality+' under kvalitetsgräns · '+r.rejectedGap+' över hårt mellanrum';
 };
'''
    if image_anchor not in text:
        print("could not install v32 recompute handler", file=sys.stderr)
        return 2
    text = text.replace(image_anchor, handler + image_anchor, 1)

    text = text.replace("SAOL live-lärande pixelannotering v31", "SAOL live-lärande pixelannotering v32", 1)
    text = text.replace("corrected-v31.json", "corrected-v32.json")
    text = text.replace(
        "<b>Hård kvalitetsgräns:</b>",
        "<b>Räkna om ordet:</b> behåller ordets manuella markeringar, kastar alla auto-kandidater och provar sedan om samtliga manuellt inlärda glyphar från alla visade rader mot just detta ord med aktuell bläck-, lod-, mellanrums- och kvalitetslogik. <b>Hård kvalitetsgräns:</b>",
        1,
    )
    out.write_text(text, encoding="utf-8")
    print("v32: per-word recompute added; plain http.server 404 no longer produces JSON.parse server-save error")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
