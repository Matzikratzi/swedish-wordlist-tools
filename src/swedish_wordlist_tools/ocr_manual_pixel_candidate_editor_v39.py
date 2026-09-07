from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from . import ocr_manual_pixel_candidate_editor_v38 as v38


def main() -> int:
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("matches")
    ap.add_argument("library")
    ap.add_argument("--out", type=Path, required=True)
    args, _ = ap.parse_known_args(sys.argv[1:])

    rc = v38.main()
    if rc or not args.out.exists():
        return rc

    text = args.out.read_text(encoding="utf-8")

    # Ignore regions are deliberately independent of glyph labels.  They mark
    # damaged/truncated source raster that the optimiser must leave unexplained.
    # Persist them with the card state so export/import keeps the decision.
    anchor = "const PERSISTENT_GLYPH_FACIT="
    if anchor not in text:
        print("could not find v39 helper anchor", file=sys.stderr)
        return 2

    helpers = r'''
function ignoredPixelsV39(state){
 const out=new Set();
 for(const r of (state.ignoreRegions||[])){
   for(let y=r.y0;y<=r.y1;y++)for(let x=r.x0;x<=r.x1;x++)out.add(x+','+y);
 }
 return out;
}
function proposalTouchesIgnoredV39(p,state){
 const ig=ignoredPixelsV39(state);
 if(!ig.size||!p.pixels)return false;
 for(const k of p.pixels)if(ig.has(k))return true;
 return false;
}
function suppressIgnoredV39(proposals,state){
 for(const p of proposals){
   if(p.status==='manual')continue;
   if(proposalTouchesIgnoredV39(p,state)){p.suppressed=true;p.ignoreSuppressed=true;}
   else if(p.ignoreSuppressed){p.suppressed=false;p.ignoreSuppressed=false;}
 }
}
function addIgnoreRegionV39(card,proposals,state,x0,y0,x1,y1){
 const W=+card.dataset.w,H=+card.dataset.h;
 const r={x0:Math.max(0,Math.min(x0,x1)),y0:Math.max(0,Math.min(y0,y1)),x1:Math.min(W-1,Math.max(x0,x1)),y1:Math.min(H-1,Math.max(y0,y1))};
 state.ignoreRegions=state.ignoreRegions||[];state.ignoreRegions.push(r);
 suppressIgnoredV39(proposals,state);
 if(typeof resolveAutoOverlaps==='function')resolveAutoOverlaps(proposals,state,card);
 if(state.render)state.render();
 return r;
}
function clearIgnoreRegionsV39(card,proposals,state){
 state.ignoreRegions=[];suppressIgnoredV39(proposals,state);
 if(typeof recomputeTargetCard==='function')recomputeTargetCard(card,proposals,state,window.__INK_V39||null);
 if(state.render)state.render();
}
'''
    text = text.replace(anchor, helpers + "\n" + anchor, 1)

    # Any candidate created from permanent facit inside an ignored region must
    # immediately disappear, including after recomputation.
    text = text.replace(
        "return {added,scanned};\n}\n\nfunction facitBaselineVotesV38",
        "suppressIgnoredV39(proposals,state);\n return {added,scanned};\n}\n\nfunction facitBaselineVotesV38",
        1,
    )

    # Add a compact per-card control.  User first draws/marks pixels using the
    # existing selection interaction, then presses Ignore selected area.  We use
    # the selected annotation's bounding box; its label is irrelevant and the
    # annotation itself is removed so it never enters glyph facit.
    marker = "function facitBaselineVotesV38(proposals){"
    ui = r'''
function installIgnoreControlV39(card,proposals,state){
 if(card.querySelector('.ignore-v39'))return;
 const host=card.querySelector('.controls')||card;
 const wrap=document.createElement('span');wrap.className='ignore-v39';wrap.style.marginLeft='8px';
 const b=document.createElement('button');b.type='button';b.textContent='Ignorera markerat område';
 const c=document.createElement('button');c.type='button';c.textContent='Rensa ignorering';c.style.marginLeft='4px';
 b.onclick=()=>{
   const p=proposals[state.selectedProposalIndex];
   if(!p||!p.pixels||!p.pixels.size){state.message='Markera först den skadade glyphen/ytan med box eller pixlar.';if(state.render)state.render();return;}
   const pts=[...p.pixels].map(k=>k.split(',').map(Number));
   const xs=pts.map(q=>q[0]),ys=pts.map(q=>q[1]);
   addIgnoreRegionV39(card,proposals,state,Math.min(...xs),Math.min(...ys),Math.max(...xs),Math.max(...ys));
   if(p.status==='manual'){const i=proposals.indexOf(p);if(i>=0)proposals.splice(i,1);}
   state.selectedProposalIndex=-1;state.message='Området ignoreras permanent vid automatisk matchning.';if(state.render)state.render();
 };
 c.onclick=()=>{state.ignoreRegions=[];for(const p of proposals){if(p.ignoreSuppressed){p.suppressed=false;p.ignoreSuppressed=false;}}if(typeof recomputeTargetCard==='function')recomputeTargetCard(card,proposals,state,window.__INK_V39||null);if(state.render)state.render();};
 wrap.append(b,c);host.appendChild(wrap);
}

'''
    text = text.replace(marker, ui + marker, 1)

    # Install controls and enforce ignored regions after every card is fully
    # initialised. allCards is the stable post-init integration point used by
    # v36-v38.
    loop = "for(const [card,proposals,state,INK] of allCards){\n const fs=facitExactHitsV38(card,proposals,state,INK);state.facitAdded=fs.added;state.facitModels=fs.scanned;\n if(!state.baselineManual)optimiseCardBaselineV36(card,proposals,state,INK);\n}"
    repl = "for(const [card,proposals,state,INK] of allCards){\n window.__INK_V39=INK;state.ignoreRegions=state.ignoreRegions||[];installIgnoreControlV39(card,proposals,state);\n const fs=facitExactHitsV38(card,proposals,state,INK);state.facitAdded=fs.added;state.facitModels=fs.scanned;suppressIgnoredV39(proposals,state);\n if(!state.baselineManual)optimiseCardBaselineV36(card,proposals,state,INK);\n}"
    if loop not in text:
        print("could not find v39 post-init loop", file=sys.stderr)
        return 2
    text = text.replace(loop, repl, 1)

    # Export state: existing exporter serialises state fields; keeping
    # ignoreRegions on state makes it part of the corrected atlas.  Add explicit
    # explanatory text so the semantics are visible in the editor.
    text = text.replace("SAOL live-lärande pixelannotering v38", "SAOL live-lärande pixelannotering v39", 1)
    text = text.replace("corrected-v38.json", "corrected-v39.json")
    text = text.replace(
        "<b>Permanent glyphfacit:</b>",
        "<b>Skadat/avklippt raster:</b> markera området med befintlig box/pixelmarkering och välj <b>Ignorera markerat område</b>. Automatiska kandidater får därefter inte använda någon pixel i området; området ska inte behöva förklaras och sparas med granskningen. <b>Permanent glyphfacit:</b>",
        1,
    )

    args.out.write_text(text, encoding="utf-8")
    print("v39: persistent ignored raster regions; selected damaged glyph areas suppress all future auto proposals")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
