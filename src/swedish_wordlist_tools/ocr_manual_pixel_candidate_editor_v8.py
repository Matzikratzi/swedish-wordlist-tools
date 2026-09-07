from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import ocr_manual_pixel_candidate_editor_v7 as v7


def main() -> int:
    """Generate v7 and improve review ordering / global live competition.

    v8 keeps the stable DOM-grid editor from v7.  It changes only presentation
    and candidate resolution semantics:

    * visible annotation chips are ordered by their left-most raster pixel;
    * every render re-runs global one-pixel/one-auto-match allocation, so newly
      propagated templates can displace older, smaller automatic candidates in
      words both before and after the source word;
    * every visibly annotated raster cell gets a bright centre dot so the exact
      selected pixel set remains obvious on top of dark source ink.
    """
    rc = v7.main()
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

    # Helpers for stable reading-order display.  Keep the proposal array itself
    # untouched because selection and export use its indices; sort only the
    # rendered chip view by the left-most (then top-most) selected pixel.
    anchor = "document.querySelectorAll('.card').forEach(card=>{"
    helpers = r'''
function proposalReadingKey(p){
 if(!p || !p.pixels || !p.pixels.size)return [Number.POSITIVE_INFINITY,Number.POSITIVE_INFINITY];
 let xmin=Number.POSITIVE_INFINITY,ymin=Number.POSITIVE_INFINITY;
 for(const k of p.pixels){
   const [x,y]=k.split(',').map(Number);
   if(x<xmin)xmin=x;
   if(y<ymin)ymin=y;
 }
 return [xmin,ymin];
}
function visibleProposalEntries(proposals){
 return proposals.map((p,i)=>({p,i,key:proposalReadingKey(p)}))
   .filter(o=>!o.p.suppressed)
   .sort((a,b)=>a.key[0]-b.key[0] || a.key[1]-b.key[1] || b.p.pixels.size-a.p.pixels.size || a.i-b.i);
}
'''
    if anchor not in text:
        raise SystemExit("could not insert v8 reading-order helpers")
    text = text.replace(anchor, helpers + "\n" + anchor, 1)

    # v7 already re-resolves overlaps in each affected card's render().  Make
    # propagation explicitly refresh every card of the same style after adding
    # a new learned form, not only cards where a candidate happened to be added.
    # This guarantees a newly learned larger candidate can replace an older
    # smaller automatic interpretation anywhere on the page.
    old_refresh = "for(const [card,proposals,state] of allCards)if(state._needsRender){state._needsRender=false;if(state.render)state.render()}"
    new_refresh = "for(const [card,proposals,state] of allCards){if(card.dataset.style===sourceCard.dataset.style && state.render)state.render();state._needsRender=false}"
    if old_refresh in text:
        text = text.replace(old_refresh, new_refresh, 1)
    else:
        # v6 tuples include the ink mask in the current generated page.
        old_refresh4 = "for(const [card,proposals,state,INK] of allCards)if(state._needsRender){state._needsRender=false;if(state.render)state.render()}"
        new_refresh4 = "for(const [card,proposals,state,INK] of allCards){if(card.dataset.style===sourceCard.dataset.style && state.render)state.render();state._needsRender=false}"
        if old_refresh4 not in text:
            raise SystemExit("could not patch v8 global propagation refresh")
        text = text.replace(old_refresh4, new_refresh4, 1)

    # Sort only the visible proposal chips in reading order.  Preserve data-i so
    # clicking a sorted chip still selects the correct underlying proposal.
    old_list = "box.innerHTML=proposals.map((p,i)=>p.suppressed?'':'<span class=\"prop '"
    new_list = "box.innerHTML=visibleProposalEntries(proposals).map(({p,i})=>'<span class=\"prop '"
    if old_list not in text:
        raise SystemExit("could not patch v8 proposal-list ordering")
    text = text.replace(old_list, new_list, 1)

    # The v7 expression ends map() with an empty suppressed branch.  Once the
    # list is pre-filtered above, remove that now-unneeded conditional tail.
    # Depending on browser-generated whitespace there is no separate token to
    # remove: the replacement above changes only the map source/expression and
    # leaves the common closing .join('') valid.

    # Add a bright dot to every cell that is part of at least one visible
    # annotation.  This is deliberately independent of label colour.
    clear_anchor = "for(let i=0;i<cells.length;i++)cells[i].style.backgroundColor='';"
    clear_repl = "for(let i=0;i<cells.length;i++){cells[i].style.backgroundColor='';cells[i].style.backgroundImage='';}"
    if clear_anchor not in text:
        raise SystemExit("could not patch v8 cell clearing")
    text = text.replace(clear_anchor, clear_repl, 1)

    paint_anchor = "cells[fy*FW+fx].style.backgroundColor=rgba(colorFor(p.label),alpha);"
    paint_repl = "cells[fy*FW+fx].style.backgroundColor=rgba(colorFor(p.label),alpha);cells[fy*FW+fx].style.backgroundImage='radial-gradient(circle at center, rgba(255,255,255,.98) 0 2px, rgba(255,255,255,0) 3px)';"
    if paint_anchor not in text:
        raise SystemExit("could not patch v8 pixel centre dots")
    text = text.replace(paint_anchor, paint_repl, 1)

    text = text.replace(
        "<h1>SAOL live-lärande pixelannotering v7</h1>",
        "<h1>SAOL live-lärande pixelannotering v8</h1>",
    )
    text = text.replace(
        "<p><b>En pixel, en match:</b>",
        "<p><b>Läsordning:</b> etiketter visas från vänster till höger efter sin vänstersta märkta pixel. <b>Retroaktiv live-konkurrens:</b> nytt facit söker både bakåt och framåt på sidan och alla auto-kandidater omprövas; en större/bättre ny träff kan därför ersätta en äldre. Varje markerad pixel har dessutom en ljus centrumprick. <b>En pixel, en match:</b>",
        1,
    )
    text = text.replace("corrected-v7", "corrected-v8")
    text = text.replace("corrected-v7.json", "corrected-v8.json")

    args.out.write_text(text, encoding="utf-8")
    print("v8: reading-order labels, retroactive live competition, bright pixel centres")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
