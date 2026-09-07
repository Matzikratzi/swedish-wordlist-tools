from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import ocr_manual_pixel_candidate_editor_v20 as v20


def main() -> int:
    rc = v20.main()
    if rc:
        return rc

    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("matches")
    ap.add_argument("library")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--scale")
    ap.add_argument("--margin")
    ap.add_argument("--ink-threshold")
    ap.add_argument("--examples-per-char")
    args, _ = ap.parse_known_args(sys.argv[1:])

    text = args.out.read_text(encoding="utf-8")

    anchor = "document.querySelectorAll('.card').forEach(card=>{"
    helper = r'''
function alignAnnotationsToInk(proposals,INK,W,H){
 const trusted=proposals.filter(p=>p.status==='manual' && p.pixels && p.pixels.size);
 if(!trusted.length)return {dx:0,dy:0,score:0,total:0};
 let best={dx:0,dy:0,score:-1,total:0};
 for(let dy=-2;dy<=2;dy++)for(let dx=-2;dx<=2;dx++){
   let score=0,total=0;
   for(const p of trusted)for(const k of p.pixels){
     const [x,y]=k.split(',').map(Number),xx=x+dx,yy=y+dy;total++;
     if(xx>=0&&yy>=0&&xx<W&&yy<H&&INK[yy]&&INK[yy][xx])score++;
   }
   if(score>best.score || (score===best.score && Math.abs(dx)+Math.abs(dy)<Math.abs(best.dx)+Math.abs(best.dy)))best={dx,dy,score,total};
 }
 if(best.dx||best.dy){
   for(const p of trusted){
     const moved=new Set();
     for(const k of p.pixels){const [x,y]=k.split(',').map(Number);moved.add((x+best.dx)+','+(y+best.dy));}
     p.pixels=moved;
   }
 }
 return best;
}
'''
    if anchor not in text:
        raise SystemExit("could not add v21 alignment helper")
    text = text.replace(anchor, helper + "\n" + anchor, 1)

    state_anchor = "allCards.push([card,proposals,state,INK]);"
    if state_anchor not in text:
        state_anchor = "allCards.push([card,proposals,state]);"
    if state_anchor not in text:
        raise SystemExit("could not locate v21 card state anchor")
    alignment = r'''
 const registration=alignAnnotationsToInk(proposals,INK,W,H);
 if(registration.dx||registration.dy){
   state.baseline=Math.max(0,Math.min(H-1,state.baseline+registration.dy));
   card.dataset.baseline=String(state.baseline);
   const bi=card.querySelector('.baseline');if(bi)bi.value=state.baseline;
   state.baselineManual=true;
   card.dataset.registrationDx=String(registration.dx);
   card.dataset.registrationDy=String(registration.dy);
   card.dataset.registrationScore=String(registration.score);
 }
'''
    text = text.replace(state_anchor, alignment + "\n " + state_anchor, 1)

    legend_anchor = "renderList();"
    if legend_anchor in text:
        text = text.replace(
            legend_anchor,
            legend_anchor + "\n   if(card.dataset.registrationDx||card.dataset.registrationDy){const l=card.querySelector('.legend');if(l)l.textContent += ' · registrering dx='+card.dataset.registrationDx+' dy='+card.dataset.registrationDy+' ('+card.dataset.registrationScore+' bläckpixlar)';}",
            1,
        )

    text = text.replace("SAOL live-lärande pixelannotering v20", "SAOL live-lärande pixelannotering v21", 1)
    text = text.replace("corrected-v20.json", "corrected-v21.json")
    text = text.replace(
        "<p><b>Pixelvisning:</b>",
        "<p><b>Bildregistrering:</b> när ett sparat facit återöppnas provas en gemensam förskjutning ±2 px mot det faktiska svarta bläcket i ord-bilden. Bästa överlapp flyttar både annotationerna och baseline_y innan omröstning/matchning körs. <b>Pixelvisning:</b>",
        1,
    )

    args.out.write_text(text, encoding="utf-8")
    print("v21: register resumed manual annotations to actual source ink before baseline/matching")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
