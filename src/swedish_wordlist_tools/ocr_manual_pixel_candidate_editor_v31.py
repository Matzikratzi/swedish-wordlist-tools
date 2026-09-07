from __future__ import annotations

import re
import sys
from pathlib import Path

from . import ocr_manual_pixel_candidate_editor_v30 as v30


MIN_RELATIVE_SCORE = 0.65
LOD_LABELS_JS = "new Set(['·','|','¦'])"


def main() -> int:
    argv = sys.argv[1:]
    out: Path | None = None
    if "--out" in argv:
        i = argv.index("--out")
        if i + 1 < len(argv):
            out = Path(argv[i + 1])

    rc = v30.main()
    if rc or out is None or not out.exists():
        return rc

    text = out.read_text(encoding="utf-8")

    # Geometry helpers.  A learned glyph can remember its horizontal distance to
    # the nearest lod/half-lod marker on the source row.  On a target row the
    # same relation is strong evidence because the source is digitally typeset,
    # not noisy OCR from a degraded scan.
    anchor = "function propagateFinished(sourceCard,sourceProposal,sourceState){"
    helpers = f'''const LOD_LABELS={LOD_LABELS_JS};
const MIN_RELATIVE_GLYPH_SCORE={MIN_RELATIVE_SCORE};
function proposalBounds(p){{
 let xmin=Infinity,xmax=-Infinity,ymin=Infinity,ymax=-Infinity;
 for(const k of p.pixels||[]){{const [x,y]=k.split(',').map(Number);xmin=Math.min(xmin,x);xmax=Math.max(xmax,x);ymin=Math.min(ymin,y);ymax=Math.max(ymax,y)}}
 return Number.isFinite(xmin)?{{xmin,xmax,ymin,ymax,cx:(xmin+xmax)/2,cy:(ymin+ymax)/2}}:null;
}}
function nearestLodDistance(proposals,p,manualOnly=false){{
 const b=proposalBounds(p);if(!b)return null;
 let best=null;
 for(const q of proposals){{
   if(q===p || !LOD_LABELS.has(q.label) || !q.pixels || !q.pixels.size)continue;
   if(manualOnly && q.status!=='manual')continue;
   const qb=proposalBounds(q);if(!qb)continue;
   const dx=qb.cx-b.cx;
   if(best===null || Math.abs(dx)<Math.abs(best))best=dx;
 }}
 return best;
}}
function relativeGlyphScore(p){{
 const total=Math.max(1,+p.total||p.pixels?.size||1);
 const raw=Number.isFinite(+p.score)?+p.score:(+p.matched||p.pixels?.size||0)-2*(+p.missing||0)-(+p.extra||0);
 const lodPenalty=Number.isFinite(+p.lod_distance_error)?4*Math.abs(+p.lod_distance_error):0;
 return (raw-lodPenalty)/total;
}}
'''
    if anchor not in text:
        print("could not add v31 geometry helpers", file=sys.stderr)
        return 2
    text = text.replace(anchor, helpers + "\n" + anchor, 1)

    # Add source separator context to each propagated glyph.  We only learn this
    # from a manual separator on the source row; an automatic separator must not
    # teach geometry recursively.
    source_line = "const sourceStyle=proposalStyle(sourceProposal,sourceCard);"
    source_repl = source_line + "\n const sourceTuple=allCards.find(t=>t[0]===sourceCard);\n const sourceLodDx=sourceTuple?nearestLodDistance(sourceTuple[1],sourceProposal,true):null;"
    if source_line not in text:
        print("could not patch v31 source lod context", file=sys.stderr)
        return 2
    text = text.replace(source_line, source_repl, 1)

    # At each target placement compare the actual nearest lod distance with the
    # source relation. One-pixel errors are deliberately expensive; >=2 px is a
    # hard rejection.  If no target lod is known yet we keep the candidate but it
    # receives no geometry bonus/penalty until row resolution.
    push_old = "proposals.push({label:sourceProposal.label,style:sourceStyle,status:(missing||extra||context)?'propagated-context':'propagated-exact',pixels:abs,contacts:[],external_contacts:0,missing,extra,score,matched,total,propagated_from:sourceCard.dataset.subnr,baseline_hint:impliedBaseline,baseline_dy:impliedBaseline-state.baseline});"
    push_new = "const temp={label:sourceProposal.label,style:sourceStyle,status:(missing||extra||context)?'propagated-context':'propagated-exact',pixels:abs,contacts:[],external_contacts:0,missing,extra,score,matched,total,propagated_from:sourceCard.dataset.subnr,baseline_hint:impliedBaseline,baseline_dy:impliedBaseline-state.baseline,lod_source_dx:sourceLodDx};\n       const targetLodDx=sourceLodDx===null?null:nearestLodDistance(proposals,temp,false);\n       if(sourceLodDx!==null && targetLodDx!==null){temp.lod_distance_error=Math.abs(targetLodDx-sourceLodDx);if(temp.lod_distance_error>=2)continue;}\n       const rel=(score-(Number.isFinite(temp.lod_distance_error)?4*temp.lod_distance_error:0))/Math.max(1,total);\n       if(rel<MIN_RELATIVE_GLYPH_SCORE)continue;temp.relative_score=rel;\n       proposals.push(temp);"
    if push_old not in text:
        print("could not patch v31 propagated score gate", file=sys.stderr)
        return 2
    text = text.replace(push_old, push_new, 1)

    # v30's row resolver gets the same relative gate. This also filters older or
    # precomputed candidates that have total/matched/missing/extra but no explicit
    # relative_score field.
    automatic_anchor = "if(conflicts(occupiedManual,p) || crossesHardBlank(p)){p.suppressed=true;continue}"
    automatic_repl = automatic_anchor + "\n   const rel=relativeGlyphScore(p);p.relative_score=rel;if(rel<MIN_RELATIVE_GLYPH_SCORE){p.suppressed=true;continue}"
    if automatic_anchor not in text:
        print("could not patch v31 resolver quality gate", file=sys.stderr)
        return 2
    text = text.replace(automatic_anchor, automatic_repl, 1)

    # Make lod-distance mismatch dominate close row-allocation decisions.
    old_weight = "return p.pixels.size + 0.45*quality;"
    new_weight = "const rel=relativeGlyphScore(p);return p.pixels.size + 0.45*quality + 8*rel - (Number.isFinite(+p.lod_distance_error)?6*Math.abs(+p.lod_distance_error):0);"
    if old_weight not in text:
        print("could not patch v31 resolver weight", file=sys.stderr)
        return 2
    text = text.replace(old_weight, new_weight, 1)

    # Add a per-card action that removes every proposal with the chosen label.
    # The label comes from the selected proposal if there is one, otherwise from
    # the label input.  It intentionally removes manual + automatic matches: the
    # user asked for a quick way to clear a troublesome letter completely.
    clear_btn = '<button class="clear" type="button">Rensa ordet</button>'
    clear_repl = clear_btn + '<button class="clear-label" type="button">Rensa bokstav</button>'
    if clear_btn not in text:
        print("could not add v31 clear-label button", file=sys.stderr)
        return 2
    text = text.replace(clear_btn, clear_repl)

    clear_handler = "card.querySelector('.clear').onclick=()=>{if(confirm('Rensa alla förslag för detta ord?')){proposals.length=0;state.selected=null;render()}};"
    clear_label_handler = clear_handler + r'''
 card.querySelector('.clear-label').onclick=()=>{
   let label='';
   if(state.selected!==null && proposals[state.selected])label=proposals[state.selected].label||'';
   if(!label){const q=parseLabelStyle(card.querySelector('.label').value,card.dataset.style);label=q.label||'';}
   if(!label || label==='?')return;
   const before=proposals.length;
   for(let i=proposals.length-1;i>=0;i--)if(proposals[i].label===label)proposals.splice(i,1);
   state.selected=proposals.length?Math.min(state.selected??0,proposals.length-1):null;
   card.querySelector('.legend').textContent='Rensade '+(before-proposals.length)+' träffar för '+label;
   render();
 };'''
    if clear_handler not in text:
        print("could not add v31 clear-label handler", file=sys.stderr)
        return 2
    text = text.replace(clear_handler, clear_label_handler, 1)

    # Show relative quality and separator error in candidate chips while tuning.
    old_display = "+p.label+' ['+proposalStyle(p,card)+'] · '+p.status+' · '+p.pixels.size+' px'"
    new_display = "+p.label+' ['+proposalStyle(p,card)+'] · '+p.status+' · '+p.pixels.size+' px'+(Number.isFinite(p.relative_score)?' · '+Math.round(100*p.relative_score)+'%':'')+(Number.isFinite(p.lod_distance_error)?' · lod Δ'+p.lod_distance_error:'')"
    if old_display in text:
        text = text.replace(old_display, new_display)

    text = text.replace("SAOL live-lärande pixelannotering v30", "SAOL live-lärande pixelannotering v31", 1)
    text = text.replace("corrected-v30.json", "corrected-v31.json")
    text = text.replace(
        "<b>Helradsoptimering:</b>",
        "<b>Hård kvalitetsgräns:</b> en automatisk glyph måste nå minst 65 % av sin egen möjliga rasterpoäng. Avståndet till närmaste manuellt inlärda lod/halvlod är stark geometri: 1 px fel kostar mycket och 2 px eller mer underkänns. <b>Rensa bokstav:</b> välj en träff eller skriv etiketten och klicka ‘Rensa bokstav’ för att ta bort samtliga träffar med den etiketten på kortet. <b>Helradsoptimering:</b>",
        1,
    )
    out.write_text(text, encoding="utf-8")
    print("v31: >=65% relative glyph score required; lod distance strongly penalized; per-card clear-label action added")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
