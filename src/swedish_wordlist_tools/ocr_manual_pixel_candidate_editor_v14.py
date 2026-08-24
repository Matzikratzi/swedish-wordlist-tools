from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import ocr_manual_pixel_candidate_editor_v13 as v13


def main() -> int:
    """Generate v13 and add left/right keyboard navigation between visible labels.

    Clicking anywhere in a card makes it the active review card.  When that card
    has a selected visible annotation, ArrowLeft/ArrowRight selects the preceding
    or following visible annotation in reading order.  v9's selected-annotation
    spotlight therefore follows automatically.
    """
    rc = v13.main()
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

    # Install after all per-card state/render hooks exist, before the export
    # handler. visibleProposalEntries() comes from v8 and already implements the
    # exact reading-order semantics used by the annotation chips.
    anchor = "document.querySelector('#export').onclick=()=>{"
    helper = r'''
let activeGlyphReviewTuple=null;
for(const tuple of allCards){
 const [card,proposals,state]=tuple;
 card.addEventListener('pointerdown',()=>{activeGlyphReviewTuple=tuple;},{capture:true});
 // Keyboard focus on a chip-equivalent card interaction should also establish
 // which row the arrows belong to.
 card.addEventListener('focusin',()=>{activeGlyphReviewTuple=tuple;});
}
function moveSelectedGlyph(delta){
 if(!activeGlyphReviewTuple)return false;
 const [card,proposals,state]=activeGlyphReviewTuple;
 if(state.selected===null || state.selected===undefined)return false;
 const visible=visibleProposalEntries(proposals);
 if(!visible.length)return false;
 const pos=visible.findIndex(o=>o.i===state.selected);
 if(pos<0)return false;
 const next=pos+delta;
 if(next<0 || next>=visible.length)return false;
 state.selected=visible[next].i;
 const label=card.querySelector('.label');
 if(label)label.value='';
 if(state.render)state.render();
 const chip=card.querySelector('.prop.selected');
 if(chip)chip.scrollIntoView({block:'nearest',inline:'nearest'});
 return true;
}
document.addEventListener('keydown',e=>{
 if(e.key!=='ArrowLeft' && e.key!=='ArrowRight')return;
 const t=e.target;
 // Never steal cursor movement / select changes from editable controls.
 if(t && (t.tagName==='INPUT' || t.tagName==='TEXTAREA' || t.tagName==='SELECT' || t.isContentEditable))return;
 if(moveSelectedGlyph(e.key==='ArrowLeft'?-1:1))e.preventDefault();
});
'''
    if anchor not in text:
        raise SystemExit("could not install v14 arrow-key navigation")
    text = text.replace(anchor, helper + "\n" + anchor, 1)

    text = text.replace(
        "<h1>SAOL live-lärande pixelannotering v13</h1>",
        "<h1>SAOL live-lärande pixelannotering v14</h1>",
        1,
    )
    text = text.replace(
        "<p><b>Blandad stil på samma tryckrad:</b>",
        "<p><b>Snabb glyphgranskning:</b> klicka en etikett; vänster/högerpil väljer sedan föregående/nästa synliga etikett i läsordning och ficklampans ljuspunkter följer den valda glyphen. Piltangenterna lämnas orörda när du skriver i ett fält eller använder stilväljaren. <b>Blandad stil på samma tryckrad:</b>",
        1,
    )
    text = text.replace("corrected-v13", "corrected-v14")
    text = text.replace("corrected-v13.json", "corrected-v14.json")

    args.out.write_text(text, encoding="utf-8")
    print("v14: ArrowLeft/ArrowRight navigate visible annotations in reading order")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
