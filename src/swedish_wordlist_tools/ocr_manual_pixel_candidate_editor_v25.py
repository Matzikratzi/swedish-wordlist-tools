from __future__ import annotations

import sys
from pathlib import Path

from . import ocr_manual_pixel_candidate_editor_v24 as v24


def main() -> int:
    argv = sys.argv[1:]
    out: Path | None = None
    if "--out" in argv:
        i = argv.index("--out")
        if i + 1 < len(argv):
            out = Path(argv[i + 1])

    rc = v24.main()
    if rc or out is None or not out.exists():
        return rc

    text = out.read_text(encoding="utf-8")

    old = (
        "const b=card.querySelector('.baseline');"
        "b.onchange=()=>{state.baseline=Math.max(0,Math.min(H-1,+b.value));"
        "state.baselineManual=true;b.value=state.baseline;render()};"
    )
    new = r'''const b=card.querySelector('.baseline');
b.onchange=()=>{
 const oldBaseline=state.baseline;
 const newBaseline=Math.max(0,Math.min(H-1,+b.value));
 const dy=newBaseline-oldBaseline;
 if(dy){
   // A manual baseline correction means the whole inferred vertical registration
   // of this word was off by dy. Move every annotation/candidate by the same
   // amount so its geometry relative to the baseline stays unchanged.
   for(const p of proposals){
     if(!p.pixels || !p.pixels.size)continue;
     const moved=new Set();
     for(const k of p.pixels){
       const [x,y]=k.split(',').map(Number);
       const yy=y+dy;
       if(yy>=0 && yy<H)moved.add(x+','+yy);
     }
     p.pixels=moved;
     if(Array.isArray(p.contacts)){
       p.contacts=p.contacts.map(q=>Array.isArray(q)&&q.length>=2?[q[0],q[1]+dy]:q);
     }
   }
 }
 state.baseline=newBaseline;
 state.baselineManual=true;
 state.baselineVotes=0;
 card.dataset.baseline=String(newBaseline);
 b.value=newBaseline;
 render();
};'''

    if old not in text:
        print("could not patch v25 manual baseline handler", file=sys.stderr)
        return 2
    text = text.replace(old, new, 1)

    text = text.replace("SAOL live-lärande pixelannotering v24", "SAOL live-lärande pixelannotering v25", 1)
    text = text.replace("corrected-v24.json", "corrected-v25.json")
    text = text.replace(
        "<b>Roman-baslinje:</b>",
        "<b>Manuell stödlinje:</b> när du flyttar stödlinjen flyttas alla färgmarkerade annotationer och kandidater lika många rasterrader, så deras läge relativt stödlinjen bevaras. <b>Roman-baslinje:</b>",
        1,
    )

    out.write_text(text, encoding="utf-8")
    print("v25: manual baseline changes translate all annotation pixels by the same dy")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
