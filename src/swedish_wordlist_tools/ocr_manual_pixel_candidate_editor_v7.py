from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import ocr_manual_pixel_candidate_editor_v6 as v6


def main() -> int:
    """Generate v6 and enforce one-use-per-pixel global candidate resolution.

    Manual annotations remain authoritative. Automatic candidates compete across
    labels within each word: largest pixel set first, then stronger status. Any
    candidate sharing even one pixel with an already chosen candidate is hidden.
    """
    rc = v6.main()
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

    anchor = "document.querySelectorAll('.card').forEach(card=>{"
    helpers = r'''
function candidatePriority(p){
 if(p.status==='manual')return 100;
 if(p.status==='accepted' || p.status==='propagated-exact')return 30;
 if(p.status==='propagated-context')return 20;
 return 10;
}
function resolveCandidateOverlaps(proposals){
 // Manual markings are user-authored and therefore reserve their pixels first.
 // Automatic proposals then compete globally: larger explained ink wins.  This
 // prevents tiny templates such as '.' from hiding inside p/l/o/etc.
 for(const p of proposals)p.suppressed=false;
 const occupied=new Set();
 const manual=proposals.filter(p=>p.status==='manual');
 for(const p of manual)for(const k of p.pixels)occupied.add(k);
 const automatic=proposals
   .filter(p=>p.status!=='manual')
   .sort((a,b)=>b.pixels.size-a.pixels.size || candidatePriority(b)-candidatePriority(a));
 let suppressed=0;
 for(const p of automatic){
   let overlap=false;
   for(const k of p.pixels)if(occupied.has(k)){overlap=true;break}
   if(overlap){p.suppressed=true;suppressed++;continue}
   for(const k of p.pixels)occupied.add(k);
 }
 return suppressed;
}
'''
    if anchor not in text:
        raise SystemExit("could not insert overlap resolver")
    text = text.replace(anchor, helpers + "\n" + anchor, 1)

    # Keep the overlap count on the per-card state object. renderList() is a
    # sibling function of render(), so a local const inside render() is not in
    # scope there; using state also prevents one card's count leaking to another.
    render_anchor = "function render(){"
    if render_anchor not in text:
        raise SystemExit("could not patch render")
    text = text.replace(
        render_anchor,
        "function render(){\n   state.overlapSuppressed=resolveCandidateOverlaps(proposals);",
        1,
    )

    # Suppressed proposals should neither paint pixels nor appear as selectable
    # candidates. Keep them in memory so they can return if the winning proposal
    # is later deleted manually.
    old_loop = "for(let pi=0;pi<proposals.length;pi++){const p=proposals[pi],alpha="
    new_loop = "for(let pi=0;pi<proposals.length;pi++){const p=proposals[pi];if(p.suppressed)continue;const alpha="
    if old_loop not in text:
        raise SystemExit("could not patch render pixel loop")
    text = text.replace(old_loop, new_loop, 1)

    old_list = "box.innerHTML=proposals.map((p,i)=>'<span class=\"prop '"
    new_list = "box.innerHTML=proposals.map((p,i)=>p.suppressed?'':'<span class=\"prop '"
    if old_list not in text:
        raise SystemExit("could not patch proposal list")
    text = text.replace(old_list, new_list, 1)

    # Display how many candidates were removed by the global allocation. This is
    # useful while validating the rule, especially for punctuation inside glyphs.
    list_tail = "box.querySelectorAll('.prop').forEach(el=>el.onclick=()=>{state.selected=+el.dataset.i;card.querySelector('.label').value='';render();});"
    list_repl = list_tail + "\n   if(state.overlapSuppressed)card.querySelector('.legend').textContent='Överlapp: '+state.overlapSuppressed+' mindre auto-matchningar bortsorterade';"
    if list_tail in text:
        text = text.replace(list_tail, list_repl, 1)

    # Export only winners (and manual annotations), never suppressed alternatives.
    export_anchor = "for(const p of proposals){if(!p.label||!p.pixels.size)continue;"
    export_repl = "for(const p of proposals){if(p.suppressed)continue;if(!p.label||!p.pixels.size)continue;"
    if export_anchor not in text:
        raise SystemExit("could not patch export")
    text = text.replace(export_anchor, export_repl, 1)

    text = text.replace(
        "<h1>SAOL live-lärande pixelannotering v6</h1>",
        "<h1>SAOL live-lärande pixelannotering v7</h1>",
    )
    text = text.replace(
        "<p><b>Live-lärande:</b>",
        "<p><b>En pixel, en match:</b> auto-kandidater löses globalt per ord. Största matchningen tar sina pixlar först; alla mindre kandidater som delar någon av dessa pixlar döljs. Detta gör att p/l vinner över falska punktmatchningar inuti dem. <b>Live-lärande:</b>",
        1,
    )
    text = text.replace("corrected-v6", "corrected-v7")
    text = text.replace("corrected-v6.json", "corrected-v7.json")

    args.out.write_text(text, encoding="utf-8")
    print("v7 overlap resolution: each auto-matched pixel is used once; largest match wins")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
