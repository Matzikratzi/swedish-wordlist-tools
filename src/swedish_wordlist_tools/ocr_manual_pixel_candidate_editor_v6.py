from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import ocr_manual_pixel_candidate_editor_v5 as v5


def main() -> int:
    """Generate v5 and add in-browser exact-shape propagation.

    A manual annotation is considered finished when the user starts the next
    label.  At that point its normalized raster shape and baseline offset are
    searched across every other visible word of the same style.  Hits are added
    only as review candidates; they never silently become trusted annotations.
    """
    rc = v5.main()
    if rc:
        return rc

    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("matches")
    ap.add_argument("library")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--scale")
    ap.add_argument("--margin")
    ap.add_argument("--ink-threshold")
    args, _ = ap.parse_known_args(sys.argv[1:])

    text = args.out.read_text(encoding="utf-8")

    # Keep each card's ink mask reachable by the global propagator.
    old_push = "allCards.push([card,proposals,state]);"
    new_push = "allCards.push([card,proposals,state,INK]);"
    if old_push not in text:
        raise SystemExit("could not patch allCards payload")
    text = text.replace(old_push, new_push)

    # Add visual class for live-propagated suggestions.
    text = text.replace(
        ".accepted{background:#e8f7eb}.rejected{background:#fff3cd}.manual{background:#e8f1ff}",
        ".accepted{background:#e8f7eb}.rejected{background:#fff3cd}.manual{background:#e8f1ff}.propagated{background:#e9ddff}.propagatedwarn{background:#ffe6b8}",
    )

    # Render propagated candidates distinctly.
    old_class_expr = "(p.status==='accepted'?'accepted':p.status==='manual'?'manual':'rejected')"
    new_class_expr = "(p.status==='accepted'?'accepted':p.status==='manual'?'manual':p.status==='propagated-exact'?'propagated':p.status==='propagated-context'?'propagatedwarn':'rejected')"
    if old_class_expr not in text:
        raise SystemExit("could not patch proposal status classes")
    text = text.replace(old_class_expr, new_class_expr)

    # Install propagation helpers immediately before card setup.  Shapes are
    # translation-normalized; vertical placement is constrained by baseline.
    anchor = "document.querySelectorAll('.card').forEach(card=>{"
    helpers = r'''
function normManualShape(pixels,baseline){
 const pts=[...pixels].map(k=>k.split(',').map(Number));
 if(!pts.length)return null;
 const xmin=Math.min(...pts.map(p=>p[0])),ymin=Math.min(...pts.map(p=>p[1]));
 const shape=pts.map(([x,y])=>[x-xmin,y-ymin]).sort((a,b)=>a[1]-b[1]||a[0]-b[0]);
 const width=Math.max(...shape.map(p=>p[0]))+1,height=Math.max(...shape.map(p=>p[1]))+1;
 return {shape,width,height,baselineOffset:baseline-ymin};
}
function samePixelSet(a,b){
 if(a.size!==b.size)return false;
 for(const x of a)if(!b.has(x))return false;
 return true;
}
function hasDetachedContextInk(INK,W,H,x0,y0,width,height,shapeSet){
 // Detect disconnected marks immediately above/around a candidate.  This is
 // intentionally only a warning: e.g. an o-ring inside ö must not be silently
 // accepted as plain o, while legitimate punctuation remains reviewable.
 const xa=Math.max(0,x0-1),xb=Math.min(W-1,x0+width);
 const ya=Math.max(0,y0-3),yb=Math.min(H-1,y0+height+1);
 for(let y=ya;y<=yb;y++)for(let x=xa;x<=xb;x++){
   if(!INK[y]||!INK[y][x])continue;
   if(shapeSet.has(x+','+y))continue;
   if(y < y0 || y >= y0+height)return true;
 }
 return false;
}
function propagateFinished(sourceCard,sourceProposal,sourceState){
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
       let ok=true;const abs=new Set();
       for(const [dx,ddy] of model.shape){const x=x0+dx,y=y0+ddy;if(!INK[y]||!INK[y][x]){ok=false;break}abs.add(x+','+y)}
       if(!ok)continue;
       // Require exact ink inside the template bbox. Extra disconnected ink
       // outside the bbox is retained as a contextual warning, not rejection.
       for(let y=y0;y<y0+model.height&&ok;y++)for(let x=x0;x<x0+model.width;x++)if(INK[y][x]&&!abs.has(x+','+y)){ok=false;break}
       if(!ok)continue;
       if(proposals.some(p=>p.label===sourceProposal.label && samePixelSet(p.pixels,abs)))continue;
       const context=hasDetachedContextInk(INK,W,H,x0,y0,model.width,model.height,abs);
       proposals.push({label:sourceProposal.label,status:context?'propagated-context':'propagated-exact',pixels:abs,contacts:[],external_contacts:0,missing:0,extra:0,propagated_from:sourceCard.dataset.subnr,baseline_dy:dy});
       added++;
     }
   }
   if(added)state._needsRender=true;
 }
 // Refresh all affected cards through their registered render hook.
 for(const [card,proposals,state] of allCards)if(state._needsRender){state._needsRender=false;if(state.render)state.render()}
 return added;
}
'''
    if anchor not in text:
        raise SystemExit("could not insert propagation helpers")
    text = text.replace(anchor, helpers + "\n" + anchor, 1)

    # Expose each card's render function to the global propagation routine.
    render_anchor = "function render(){"
    render_repl = "function render(){"
    # Add assignment just before the initial render near end of per-card setup.
    init_anchor = "if(state.selected!==null)card.querySelector('.label').value=proposals[state.selected].label;\n render();"
    init_repl = "if(state.selected!==null)card.querySelector('.label').value=proposals[state.selected].label;\n state.render=render;\n render();"
    if init_anchor not in text:
        raise SystemExit("could not expose render hook")
    text = text.replace(init_anchor, init_repl)

    # v5's startNewLabel finalizes the current manual annotation before creating
    # the next one.  This matches the user's 1 -> 2 -> 3 goto 1 workflow.
    old_start = """function startNewLabel(){
   const label=labelInput.value.trim();
   if(!label)return;
   proposals.push({label,status:'manual',pixels:new Set(),contacts:[],external_contacts:0,missing:0,extra:0});
   state.selected=proposals.length-1;
   labelInput.value='';
   render();
 }"""
    new_start = """function startNewLabel(){
   const label=labelInput.value.trim();
   if(!label)return;
   if(state.selected!==null){
     const finished=proposals[state.selected];
     const n=propagateFinished(card,finished,state);
     if(n)card.querySelector('.legend').textContent='Live-sökning: '+n+' nya kandidater från '+finished.label;
   }
   proposals.push({label,status:'manual',pixels:new Set(),contacts:[],external_contacts:0,missing:0,extra:0});
   state.selected=proposals.length-1;
   labelInput.value='';
   render();
 }"""
    if old_start not in text:
        raise SystemExit("could not patch startNewLabel")
    text = text.replace(old_start, new_start, 1)

    # Export loop now receives a 4-tuple.
    text = text.replace("for(const [card,proposals,state] of allCards){", "for(const [card,proposals,state,INK] of allCards){")

    text = text.replace(
        "<h1>SAOL autoannotering → manuell korrigering v5</h1>",
        "<h1>SAOL live-lärande pixelannotering v6</h1>",
    )
    text = text.replace(
        "<p><b>Arbetsflöde:</b>",
        "<p><b>Live-lärande:</b> när du skriver nästa etikett söker sidan omedelbart efter den färdiga manuella formen i alla andra visade ord av samma stil. Lila = exakt pixel- och baseline-träff. Orange = exakt form men extra fristående bläck i närheten (t.ex. o-ringen i ö), alltså kontrollera. <b>Arbetsflöde:</b>",
        1,
    )
    text = text.replace("corrected-v5", "corrected-v6")
    text = text.replace("corrected-v5.json", "corrected-v6.json")

    args.out.write_text(text, encoding="utf-8")
    print("v6 live propagation: finished manual annotations search all visible same-style words")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
