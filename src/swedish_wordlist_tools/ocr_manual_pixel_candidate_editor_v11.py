from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import ocr_manual_pixel_candidate_editor_v10 as v10


def main() -> int:
    """Generate v10 and add an authoritative per-card roman/italic override.

    The manifest/matcher style is only the initial guess.  Changing the selector
    keeps manual annotations, removes automatic proposals produced under the old
    style, changes the card's data-style (which live propagation and export use),
    and then replays all finished manual examples of the newly selected style so
    the changed card can immediately receive appropriate live candidates.
    """
    rc = v10.main()
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

    # Add an explicit selector to every card. The original badge remains as a
    # compact visual indicator, but is updated together with the selector.
    old_control = '<label>Etikett <input class="label" size="8"></label>'
    new_control = (
        '<label>Etikett <input class="label" size="8"></label>\n'
        '<label>Stil <select class="style-select">'
        '<option value="italic">kursiv</option>'
        '<option value="roman">roman</option>'
        '</select></label>'
    )
    if old_control not in text:
        raise SystemExit("could not add v11 style selector")
    text = text.replace(old_control, new_control)

    # Helper: replay every finished manual annotation whose card currently has
    # the requested style. propagateFinished() already scans both earlier and
    # later cards and resolves competition through each card's render hook.
    anchor = "document.querySelectorAll('.card').forEach(card=>{"
    helper = r'''
function replayManualKnowledgeForStyle(style){
 const sources=[];
 for(const [c,ps,st] of allCards){
   if(c.dataset.style!==style)continue;
   for(const p of ps){
     if(p.status==='manual' && p.label && p.pixels && p.pixels.size) sources.push([c,p,st]);
   }
 }
 for(const [c,p,st] of sources)propagateFinished(c,p,st);
 for(const [c,ps,st] of allCards)if(c.dataset.style===style && st.render)st.render();
}
'''
    if anchor not in text:
        raise SystemExit("could not insert v11 style helper")
    text = text.replace(anchor, helper + "\n" + anchor, 1)

    # Install selector after the per-card render hook is available.  Automatic
    # proposals are style-dependent and must not survive a style correction;
    # human annotations do survive because they are the authoritative evidence.
    init_anchor = "state.render=render;\n render();"
    init_repl = r'''state.render=render;
 const styleSelect=card.querySelector('.style-select');
 const styleBadge=card.querySelector('.badge');
 styleSelect.value=card.dataset.style;
 styleSelect.onchange=()=>{
   const oldStyle=card.dataset.style;
   const newStyle=styleSelect.value;
   if(newStyle===oldStyle)return;
   card.dataset.style=newStyle;
   if(styleBadge)styleBadge.textContent=newStyle;

   // Preserve only user-authored annotations. Everything inferred by the old
   // font/style is invalid after an override and is regenerated from live manual
   // knowledge of the chosen style.
   const manual=proposals.filter(p=>p.status==='manual');
   proposals.splice(0,proposals.length,...manual);
   state.selected=proposals.length?0:null;
   state.baselineManual=false;
   state.baselineVotes=0;
   render();
   replayManualKnowledgeForStyle(newStyle);
   card.querySelector('.legend').textContent='Stil manuellt satt till '+newStyle+' · auto-förslag omräknade';
 };
 render();'''
    if init_anchor not in text:
        raise SystemExit("could not install v11 style selector handler")
    text = text.replace(init_anchor, init_repl, 1)

    text = text.replace(
        "<h1>SAOL live-lärande pixelannotering v10</h1>",
        "<h1>SAOL live-lärande pixelannotering v11</h1>",
    )
    text = text.replace(
        "<p><b>Glyph-röstad stödlinje:</b>",
        "<p><b>Stil per rad:</b> matcherens roman/kursiv-gissning är bara startvärde. Du kan byta stil på varje ordkort; manuella annotationer behålls, gamla auto-förslag från fel stil tas bort och den valda stilens live-facit räknas om. <b>Glyph-röstad stödlinje:</b>",
        1,
    )
    text = text.replace("corrected-v10", "corrected-v11")
    text = text.replace("corrected-v10.json", "corrected-v11.json")

    args.out.write_text(text, encoding="utf-8")
    print("v11: authoritative per-card roman/italic selector with live recomputation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
