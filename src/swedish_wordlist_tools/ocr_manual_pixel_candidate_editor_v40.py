from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import ocr_manual_pixel_candidate_editor_v39 as v39


def main() -> int:
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("matches")
    ap.add_argument("library")
    ap.add_argument("--out", type=Path, required=True)
    args, _ = ap.parse_known_args(sys.argv[1:])

    rc = v39.main()
    if rc or not args.out.exists():
        return rc

    text = args.out.read_text(encoding="utf-8")
    anchor = "function ignoredPixelsV39(state){"
    if anchor not in text:
        print("could not find v40 debug helper anchor", file=sys.stderr)
        return 2

    helpers = r'''
function serialiseProposalV40(p){
 const out={};
 for(const [k,v] of Object.entries(p)){
   if(k==='pixels')out.pixels=[...(v||[])].map(s=>s.split(',').map(Number));
   else if(v instanceof Set)out[k]=[...v];
   else if(typeof v!=='function')out[k]=v;
 }
 return out;
}
function blackPixelsV40(INK,W,H){
 const pts=[];
 for(let y=0;y<H;y++)for(let x=0;x<W;x++)if(INK[y]&&INK[y][x])pts.push([x,y]);
 return pts;
}
function downloadJsonV40(name,payload){
 const blob=new Blob([JSON.stringify(payload,null,2)+'\n'],{type:'application/json'});
 const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=name;document.body.appendChild(a);a.click();
 setTimeout(()=>{URL.revokeObjectURL(a.href);a.remove();},1000);
}
function safeSlugV40(s){return String(s||'word').normalize('NFKD').replace(/[^A-Za-z0-9åäöÅÄÖ_-]+/g,'_').replace(/^_+|_+$/g,'')||'word';}
function buildWordDebugV40(card,proposals,state,INK){
 const W=+card.dataset.w,H=+card.dataset.h;
 const ds={};for(const [k,v] of Object.entries(card.dataset))ds[k]=v;
 const manual=proposals.filter(p=>p.status==='manual').map(serialiseProposalV40);
 const ignored=state.ignoreRegions||[];
 const debug={
   format:'saol14-word-debug-v1',
   expected_word:card.dataset.word||card.dataset.expectedWord||card.dataset.headword||'',
   headword:card.dataset.headword||'',
   page:card.dataset.page||'',subnr:card.dataset.subnr||'',style:card.dataset.style||'',
   width:W,height:H,
   black_pixels:blackPixelsV40(INK,W,H),
   baseline:{
     current:state.baseline,
     manual:!!state.baselineManual,
     initial:state.autoBaselineInitial??null,
     raster_seed:state.autoBaselineRasterSeed??null,
     score:state.autoBaselineScore??null,
     tried:state.autoBaselineTried??null,
     exact_anchors:state.autoBaselineExactAnchors??null,
     votes:state.baselineVotes??null
   },
   proposals:proposals.map(serialiseProposalV40),
   manual_glyphs:manual,
   ignore_regions:ignored,
   damage:{
     truncated_or_damaged:!!state.debugDamaged,
     note:state.debugDamageNote||''
   },
   card_dataset:ds
 };
 return debug;
}
function installWordDebugV40(card,proposals,state,INK){
 if(card.querySelector('.debug-v40'))return;
 const host=card.querySelector('.controls')||card;
 const wrap=document.createElement('span');wrap.className='debug-v40';wrap.style.marginLeft='8px';
 const damaged=document.createElement('label');damaged.style.marginLeft='6px';
 const cb=document.createElement('input');cb.type='checkbox';cb.checked=!!state.debugDamaged;cb.onchange=()=>state.debugDamaged=cb.checked;
 damaged.append(cb,document.createTextNode(' skadad/trunkerad'));
 const note=document.createElement('input');note.type='text';note.placeholder='kommentar om skadan';note.value=state.debugDamageNote||'';note.style.marginLeft='4px';note.oninput=()=>state.debugDamageNote=note.value;
 const b=document.createElement('button');b.type='button';b.textContent='Exportera ord-debugg';b.style.marginLeft='4px';
 b.onclick=()=>{
   state.debugDamageNote=note.value;state.debugDamaged=cb.checked;
   const d=buildWordDebugV40(card,proposals,state,INK);
   const word=d.expected_word||d.headword||card.dataset.subnr||'word';
   downloadJsonV40('saol14-word-debug-'+safeSlugV40(word)+'.json',d);
 };
 wrap.append(damaged,note,b);host.appendChild(wrap);
}
'''
    text = text.replace(anchor, helpers + "\n" + anchor, 1)

    # Install debug controls at the same stable post-init point as v39.
    old = "window.__INK_V39=INK;state.ignoreRegions=state.ignoreRegions||[];installIgnoreControlV39(card,proposals,state);"
    new = "window.__INK_V39=INK;state.ignoreRegions=state.ignoreRegions||[];installIgnoreControlV39(card,proposals,state);installWordDebugV40(card,proposals,state,INK);"
    if old not in text:
        print("could not install v40 per-word debug control", file=sys.stderr)
        return 2
    text = text.replace(old, new, 1)

    text = text.replace("SAOL live-lärande pixelannotering v39", "SAOL live-lärande pixelannotering v40", 1)
    text = text.replace("corrected-v39.json", "corrected-v40.json")
    text = text.replace(
        "<b>Skadat/avklippt raster:</b>",
        "<b>Ord-debugg:</b> varje kort kan exporteras som ett komplett JSON-snapshot med svartpixelraster, stödlinjehistorik, alla kandidater (även suppressed/felaktiga), manuella glyphar, ignorerade områden, verkligt ord/källmetadata samt explicit markering och kommentar för skadat/trunkerat raster. Ladda upp den filen så kan problemet återskapas exakt. <b>Skadat/avklippt raster:</b>",
        1,
    )

    args.out.write_text(text, encoding="utf-8")
    print("v40: per-word debug JSON export with raster, baseline, all proposals, manual glyphs, ignore regions and damage note")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
