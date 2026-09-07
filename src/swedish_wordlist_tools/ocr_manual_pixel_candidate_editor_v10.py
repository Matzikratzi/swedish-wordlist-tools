from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import ocr_manual_pixel_candidate_editor_v9 as v9


def main() -> int:
    rc = v9.main()
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
const BASELINE_ANCHORS=new Set([..."abcdehiklmnorstuvwxåäö"]);
const STRICT_Y_LABELS=new Set(['.','·','-',',']);
function votedBaseline(proposals,current){
 const votes=new Map();
 for(const p of proposals){
   if(p.suppressed || !BASELINE_ANCHORS.has(p.label) || !p.pixels || !p.pixels.size)continue;
   let ymax=-Infinity;
   for(const k of p.pixels){const y=Number(k.split(',')[1]);if(y>ymax)ymax=y}
   if(Number.isFinite(ymax))votes.set(ymax,(votes.get(ymax)||0)+1);
 }
 let best=current,bestN=0;
 for(const [y,n] of votes){
   if(n>bestN || (n===bestN && Math.abs(y-current)<Math.abs(best-current))){best=y;bestN=n}
 }
 return {baseline:best,votes:bestN};
}
'''
    if anchor not in text:
        raise SystemExit("could not insert v10 baseline helpers")
    text = text.replace(anchor, helpers + "\n" + anchor, 1)

    # Track whether the human explicitly moved the support line. Automatic votes
    # are used only until that happens for the card.
    old_state = "let state={selected:proposals.length?0:null,baseline:+card.dataset.baseline,mode:'box',drag:false,start:null,current:null};"
    new_state = "let state={selected:proposals.length?0:null,baseline:+card.dataset.baseline,baselineManual:false,baselineVotes:0,mode:'box',drag:false,start:null,current:null};"
    if old_state not in text:
        raise SystemExit("could not patch v10 state")
    text = text.replace(old_state, new_state, 1)

    # v7 begins every render by resolving one-pixel/one-match competition. Vote
    # only from the winners, then update the red support line before painting.
    render_marker = "state.overlapSuppressed=resolveCandidateOverlaps(proposals);"
    render_vote = render_marker + "\n   if(!state.baselineManual){const bv=votedBaseline(proposals,state.baseline);state.baseline=bv.baseline;state.baselineVotes=bv.votes;card.querySelector('.baseline').value=state.baseline;}"
    if render_marker not in text:
        raise SystemExit("could not patch v10 render baseline vote")
    text = text.replace(render_marker, render_vote, 1)

    # A human change freezes the baseline for this card until reload. This keeps
    # manual corrections authoritative while retaining automatic voting elsewhere.
    old_change = "const b=card.querySelector('.baseline');b.onchange=()=>{state.baseline=Math.max(0,Math.min(H-1,+b.value));b.value=state.baseline;render()};"
    new_change = "const b=card.querySelector('.baseline');b.onchange=()=>{state.baseline=Math.max(0,Math.min(H-1,+b.value));state.baselineManual=true;b.value=state.baseline;render()};"
    if old_change not in text:
        raise SystemExit("could not patch v10 baseline manual override")
    text = text.replace(old_change, new_change, 1)

    # Tiny punctuation/separator forms must retain the exact learned vertical
    # relation to the support line. Ordinary glyphs may still search +/-1 row.
    old_dy = "for(let dy=-1;dy<=1;dy++){"
    new_dy = "for(const dy of (STRICT_Y_LABELS.has(sourceProposal.label)?[0]:[-1,0,1])){"
    if old_dy not in text:
        raise SystemExit("could not patch v10 strict-y live propagation")
    text = text.replace(old_dy, new_dy, 1)

    # Show how the current baseline was obtained without cluttering the controls.
    list_tail = "if(state.overlapSuppressed)card.querySelector('.legend').textContent='Överlapp: '+state.overlapSuppressed+' mindre auto-matchningar bortsorterade';"
    if list_tail in text:
        text = text.replace(
            list_tail,
            list_tail + "\n   if(!state.baselineManual && state.baselineVotes)card.querySelector('.legend').textContent += ' · stödlinje: '+state.baselineVotes+' glyph-röster';",
            1,
        )

    text = text.replace(
        "<h1>SAOL live-lärande pixelannotering v9</h1>",
        "<h1>SAOL live-lärande pixelannotering v10</h1>",
    )
    text = text.replace(
        "<p><b>Läsordning:</b>",
        "<p><b>Glyph-röstad stödlinje:</b> vanliga bokstäver som står på raden röstar om stödlinjens y-läge; din manuella justering vinner alltid. <b>Y är bevis:</b> ., ·, - och , får vid live-sökning bara ligga på exakt den höjd relativt stödlinjen som facit anger. <b>Läsordning:</b>",
        1,
    )
    text = text.replace("corrected-v9", "corrected-v10")
    text = text.replace("corrected-v9.json", "corrected-v10.json")

    args.out.write_text(text, encoding="utf-8")
    print("v10: glyph-voted baseline, manual override, strict y for tiny marks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
