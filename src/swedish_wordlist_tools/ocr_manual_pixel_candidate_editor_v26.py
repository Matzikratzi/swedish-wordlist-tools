from __future__ import annotations

import sys
from pathlib import Path

from . import ocr_manual_pixel_candidate_editor_v25 as v25


def main() -> int:
    argv = sys.argv[1:]
    out: Path | None = None
    if "--out" in argv:
        i = argv.index("--out")
        if i + 1 < len(argv):
            out = Path(argv[i + 1])

    rc = v25.main()
    if rc or out is None or not out.exists():
        return rc

    text = out.read_text(encoding="utf-8")

    anchor = "const allCards=[];"
    helpers = r'''
function parseLabelStyle(raw,defaultStyle){
 const s=(raw||'').trim();
 const m=s.match(/^(.*?)\s*\{\{\s*([rib])\s*\}\}\s*$/i);
 if(!m)return {label:s||'?',style:defaultStyle};
 const map={r:'roman',i:'italic',b:'bold'};
 return {label:(m[1]||'?').trim()||'?',style:map[m[2].toLowerCase()]||defaultStyle};
}
function proposalStyle(p,card){return p.style||card.dataset.style||'roman'}
function labelWithStyle(p,card){
 const st=proposalStyle(p,card),def=card.dataset.style;
 if(st===def)return p.label;
 const code=st==='roman'?'r':st==='italic'?'i':'b';
 return p.label+' {{'+code+'}}';
}
'''
    if anchor not in text:
        print("could not add v26 style helpers", file=sys.stderr)
        return 2
    text = text.replace(anchor, helpers + "\n" + anchor, 1)

    # Fuzzy propagation: learned glyphs compete on every target card regardless
    # of the target card's default style.  The source annotation's own style is
    # carried with every generated candidate.
    old_source = "if(!sourceProposal || sourceProposal.status!=='manual' || !sourceProposal.label || !sourceProposal.pixels.size)return 0;\n const model=normManualShape(sourceProposal.pixels,sourceState.baseline);if(!model)return 0;"
    new_source = "if(!sourceProposal || sourceProposal.status!=='manual' || !sourceProposal.label || !sourceProposal.pixels.size)return 0;\n const sourceStyle=proposalStyle(sourceProposal,sourceCard);\n const model=normManualShape(sourceProposal.pixels,sourceState.baseline);if(!model)return 0;"
    if old_source not in text:
        print("could not add v26 source annotation style", file=sys.stderr)
        return 2
    text = text.replace(old_source, new_source, 1)

    old_filter = "if(card===sourceCard || card.dataset.style!==sourceCard.dataset.style)continue;"
    if old_filter not in text:
        print("could not remove v26 target style filter", file=sys.stderr)
        return 2
    text = text.replace(old_filter, "if(card===sourceCard)continue;", 1)

    old_push = "proposals.push({label:sourceProposal.label,status:(missing||extra||context)?'propagated-context':'propagated-exact',pixels:abs,contacts:[],external_contacts:0,missing,extra,score,matched,total,propagated_from:sourceCard.dataset.subnr,baseline_dy:dy});"
    new_push = "proposals.push({label:sourceProposal.label,style:sourceStyle,status:(missing||extra||context)?'propagated-context':'propagated-exact',pixels:abs,contacts:[],external_contacts:0,missing,extra,score,matched,total,propagated_from:sourceCard.dataset.subnr,baseline_dy:dy});"
    if old_push not in text:
        print("could not preserve v26 propagated style", file=sys.stderr)
        return 2
    text = text.replace(old_push, new_push, 1)

    old_refresh = "for(const [card,proposals,state] of allCards){if(card.dataset.style===sourceCard.dataset.style && state.render)state.render();state._needsRender=false}"
    if old_refresh in text:
        text = text.replace(old_refresh, "for(const [card,proposals,state] of allCards){if(state.render)state.render();state._needsRender=false}", 1)

    # Manual creation from the normal Enter/new-label workflow.  Default style is
    # the card selector, but {{r}}/{{i}}/{{b}} overrides it for just this glyph.
    old_start = r'''function startNewLabel(){
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
 }'''
    new_start = r'''function startNewLabel(){
   const parsed=parseLabelStyle(labelInput.value,card.dataset.style);
   if(!parsed.label)return;
   if(state.selected!==null){
     const finished=proposals[state.selected];
     const n=propagateFinished(card,finished,state);
     if(n)card.querySelector('.legend').textContent='Live-sökning: '+n+' nya kandidater från '+finished.label+' ['+proposalStyle(finished,card)+']';
   }
   proposals.push({label:parsed.label,style:parsed.style,status:'manual',pixels:new Set(),contacts:[],external_contacts:0,missing:0,extra:0});
   state.selected=proposals.length-1;
   labelInput.value='';
   render();
 }'''
    if old_start not in text:
        print("could not patch v26 startNewLabel", file=sys.stderr)
        return 2
    text = text.replace(old_start, new_start, 1)

    # Pixel/box selection can create a proposal without first pressing Enter.
    old_ensure = "const label=card.querySelector('.label').value.trim()||'?';\n   proposals.push({label,status:'manual',pixels:new Set(),contacts:[],external_contacts:0,missing:0,extra:0});"
    new_ensure = "const parsed=parseLabelStyle(card.querySelector('.label').value,card.dataset.style);\n   proposals.push({label:parsed.label,style:parsed.style,status:'manual',pixels:new Set(),contacts:[],external_contacts:0,missing:0,extra:0});"
    if old_ensure in text:
        text = text.replace(old_ensure, new_ensure, 1)

    # Existing selected annotation edited in the label box.
    old_change = "card.querySelector('.label').onchange=e=>{if(state.selected===null)return;proposals[state.selected].label=e.target.value.trim();render()};"
    new_change = "card.querySelector('.label').onchange=e=>{if(state.selected===null)return;const q=parseLabelStyle(e.target.value,card.dataset.style);proposals[state.selected].label=q.label;proposals[state.selected].style=q.style;render()};"
    if old_change in text:
        text = text.replace(old_change, new_change, 1)

    # The explicit New button exists in the underlying editor as a second manual
    # creation path.
    old_new = "card.querySelector('.new').onclick=()=>{const label=card.querySelector('.label').value.trim()||'?';proposals.push({label,status:'manual',pixels:new Set(),contacts:[],external_contacts:0,missing:0,extra:0});state.selected=proposals.length-1;render()};"
    new_new = "card.querySelector('.new').onclick=()=>{const q=parseLabelStyle(card.querySelector('.label').value,card.dataset.style);proposals.push({label:q.label,style:q.style,status:'manual',pixels:new Set(),contacts:[],external_contacts:0,missing:0,extra:0});state.selected=proposals.length-1;render()};"
    if old_new in text:
        text = text.replace(old_new, new_new, 1)

    # Show a proposal's actual style, not merely the card default.
    old_label_display = "+p.label+' · '+p.status+' · '+p.pixels.size+' px'"
    new_label_display = "+p.label+' ['+proposalStyle(p,card)+'] · '+p.status+' · '+p.pixels.size+' px'"
    if old_label_display in text:
        text = text.replace(old_label_display, new_label_display)

    # Selecting an annotation repopulates the edit box with an explicit override
    # whenever its own style differs from the card default.
    text = text.replace(
        "card.querySelector('.label').value=proposals[state.selected].label;",
        "card.querySelector('.label').value=labelWithStyle(proposals[state.selected],card);",
    )

    # Persist style per annotation.  Older atlases without this field still work:
    # resumed proposals inherit the word/card style via proposalStyle().
    old_export = "anns.push({label:p.label,pixels,pixels_relative_to_baseline:pixels.map(([x,y])=>[x,y-state.baseline]),candidate_status:p.status})"
    new_export = "anns.push({label:p.label,style:proposalStyle(p,card),pixels,pixels_relative_to_baseline:pixels.map(([x,y])=>[x,y-state.baseline]),candidate_status:p.status})"
    if old_export not in text:
        print("could not patch v26 annotation export", file=sys.stderr)
        return 2
    text = text.replace(old_export, new_export, 1)

    text = text.replace("SAOL live-lärande pixelannotering v25", "SAOL live-lärande pixelannotering v26", 1)
    text = text.replace("corrected-v25.json", "corrected-v26.json")
    text = text.replace(
        "<b>Manuell stödlinje:</b>",
        "<b>Stil per annotation:</b> matchning provar alltid facit från roman, kursiv och fet mot varje ord. Kortets stil är bara förval för nya manuella markeringar. Skriv t.ex. <code>e {{r}}</code>, <code>e {{i}}</code> eller <code>e {{b}}</code> för att välja stil på just den annotationen; utan suffix används kortets förvalda stil. <b>Manuell stödlinje:</b>",
        1,
    )

    out.write_text(text, encoding="utf-8")
    print("v26: all styles compete on every card; per-annotation {{r}}/{{i}}/{{b}} overrides persisted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
