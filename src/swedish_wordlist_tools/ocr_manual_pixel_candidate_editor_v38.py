from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from . import ocr_manual_pixel_candidate_editor_v37 as v37


DEFAULT_FACIT = Path("glyphs/saol14-manual-glyph-facit.json")


def _load_models(path: Path) -> list[dict[str, object]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("format") != "saol14-manual-glyph-facit-v1":
        raise SystemExit(f"unsupported glyph facit format: {payload.get('format')!r}")
    models: list[dict[str, object]] = []
    for g in payload.get("glyphs", []):
        pts = g.get("pixels_relative_to_baseline") or []
        if not isinstance(pts, list) or not pts:
            continue
        clean = sorted({(int(p[0]), int(p[1])) for p in pts if isinstance(p, (list, tuple)) and len(p) == 2})
        if not clean:
            continue
        xmin = min(x for x, _ in clean)
        ymin = min(y for _, y in clean)
        xmax = max(x for x, _ in clean)
        ymax = max(y for _, y in clean)
        # Facit x is already normalized, but normalize defensively.  Convert y
        # from baseline-relative coordinates to a top-relative raster template.
        shape = [[x - xmin, y - ymin] for x, y in clean]
        models.append({
            "label": str(g.get("label") or ""),
            "style": str(g.get("style") or "roman"),
            "shape": shape,
            "width": xmax - xmin + 1,
            "height": ymax - ymin + 1,
            "baselineOffset": -ymin,
            "pixels": len(shape),
            "sourceCount": len(g.get("sources") or []),
        })
    return models


def main() -> int:
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("matches")
    ap.add_argument("library")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--glyph-facit", type=Path, default=DEFAULT_FACIT)
    args, _ = ap.parse_known_args(sys.argv[1:])

    # Hide v38-only argument from the inherited argparse chain.
    old_argv = sys.argv[:]
    try:
        stripped = []
        skip = False
        for a in sys.argv:
            if skip:
                skip = False
                continue
            if a == "--glyph-facit":
                skip = True
                continue
            stripped.append(a)
        sys.argv = stripped
        rc = v37.main()
    finally:
        sys.argv = old_argv
    if rc or not args.out.exists():
        return rc

    facit = args.glyph_facit
    if not facit.exists():
        print(f"glyph facit not found: {facit}", file=sys.stderr)
        return 2
    models = _load_models(facit)
    if not models:
        print("glyph facit contains no usable models", file=sys.stderr)
        return 2

    text = args.out.read_text(encoding="utf-8")
    anchor = "function rasterBaselineSeedV37(INK,W,H,fallback){"
    if anchor not in text:
        print("could not find v38 facit helper anchor", file=sys.stderr)
        return 2

    js_models = json.dumps(models, ensure_ascii=False, separators=(",", ":"))
    helpers = r'''
const PERSISTENT_GLYPH_FACIT=__MODELS__;

function facitExactHitsV38(card,proposals,state,INK){
 const W=+card.dataset.w,H=+card.dataset.h;
 let added=0,scanned=0;
 const seen=new Set(proposals.map(p=>p.label+'|'+(p.style||'')+'|'+[...p.pixels].sort().join(';')));
 for(const model of PERSISTENT_GLYPH_FACIT){
   if(!model.label || !model.shape || !model.shape.length)continue;
   scanned++;
   // Scan the whole small word raster.  Baseline is deliberately NOT used as
   // a placement prerequisite: exact glyph hits are allowed to tell us where
   // the baseline is, instead of being rejected by a bad initial baseline.
   for(let y0=0;y0+model.height<=H;y0++)for(let x0=0;x0+model.width<=W;x0++){
     let ok=true;const abs=new Set();
     for(const [dx,dy] of model.shape){
       const x=x0+dx,y=y0+dy;
       if(!INK[y] || !INK[y][x]){ok=false;break;}
       abs.add(x+','+y);
     }
     if(!ok)continue;
     // 100% means both directions: every template pixel is black AND every
     // black pixel inside the glyph bbox belongs to the template.  This rejects
     // a tiny half-lod template sitting inside a larger letter whenever there
     // is additional ink in its bbox.
     for(let y=y0;y<y0+model.height&&ok;y++)for(let x=x0;x<x0+model.width;x++){
       if(INK[y]&&INK[y][x]&&!abs.has(x+','+y)){ok=false;break;}
     }
     if(!ok)continue;
     const key=model.label+'|'+model.style+'|'+[...abs].sort().join(';');
     if(seen.has(key))continue;
     seen.add(key);
     proposals.push({
       label:model.label,style:model.style,status:'facit-exact',pixels:abs,
       contacts:[],external_contacts:0,missing:0,extra:0,
       score:model.pixels,matched:model.pixels,total:model.pixels,
       relative_score:1,baseline_hint:y0+model.baselineOffset,
       facit:true,facit_sources:model.sourceCount||0
     });
     added++;
   }
 }
 return {added,scanned};
}

function facitBaselineVotesV38(proposals){
 const byY=new Map();
 for(const p of proposals){
   if(!p.facit || p.suppressed || !Number.isFinite(+p.baseline_hint))continue;
   const y=+p.baseline_hint,sz=p.pixels?p.pixels.size:0;
   // Large exact glyphs carry proportionally more evidence.  Source count gives
   // only a small confidence bump; it can never make tiny fragments dominate.
   const support=sz*(1+0.03*Math.min(10,+p.facit_sources||0));
   const q=byY.get(y)||{score:0,pixels:0,count:0};
   q.score+=support;q.pixels+=sz;q.count++;byY.set(y,q);
 }
 return byY;
}
'''.replace("__MODELS__", js_models)
    text = text.replace(anchor, helpers + "\n" + anchor, 1)

    # Make exact facit hits visually equivalent to propagated exact hits.
    text = text.replace(
        "p.status==='propagated-exact'?'propagated':",
        "(p.status==='propagated-exact'||p.status==='facit-exact')?'propagated':",
        1,
    )

    # Exact-anchor score must only count candidates that survived whole-row
    # overlap optimisation. This prevents four small overlapping fragments from
    # all voting against one larger full glyph.
    text = text.replace(
        "if(p.status==='manual')continue;\n   const exact=",
        "if(p.status==='manual' || p.suppressed)continue;\n   const exact=",
        1,
    )

    # Strengthen baseline choice with persistent exact-facit votes after the row
    # resolver has decided which non-overlapping candidates actually survive.
    old_score = "const anchors=exactAnchorScoreV37(proposals,y);\n   const score=rowScore+anchors.score;"
    new_score = (
        "const anchors=exactAnchorScoreV37(proposals,y);\n"
        "   const fv=facitBaselineVotesV38(proposals).get(y)||{score:0,pixels:0,count:0};\n"
        "   const score=rowScore+anchors.score+2.5*fv.score;"
    )
    if old_score not in text:
        print("could not patch v38 baseline vote score", file=sys.stderr)
        return 2
    text = text.replace(old_score, new_score, 1)

    # Seed all cards from the permanent glyph dictionary BEFORE v37's global
    # baseline optimisation pass.  This is the architectural fix: old learning
    # no longer disappears when its source word is not one of the visible 20.
    loop = "for(const [card,proposals,state,INK] of allCards){\n if(!state.baselineManual)optimiseCardBaselineV36(card,proposals,state,INK);\n}"
    repl = "for(const [card,proposals,state,INK] of allCards){\n const fs=facitExactHitsV38(card,proposals,state,INK);state.facitAdded=fs.added;state.facitModels=fs.scanned;\n if(!state.baselineManual)optimiseCardBaselineV36(card,proposals,state,INK);\n}"
    if loop not in text:
        print("could not find v38 post-init facit seeding loop", file=sys.stderr)
        return 2
    text = text.replace(loop, repl, 1)

    # Recompute must restore persistent facit candidates as well, otherwise the
    # user would lose the dictionary after pressing "Räkna om ordet".
    old_recompute = "const r=recomputeTargetCard(card,proposals,state,INK);\n   let ob=null;if(!state.baselineManual)ob=optimiseCardBaselineV36(card,proposals,state,INK);"
    new_recompute = "const r=recomputeTargetCard(card,proposals,state,INK);\n   const fs=facitExactHitsV38(card,proposals,state,INK);\n   let ob=null;if(!state.baselineManual)ob=optimiseCardBaselineV36(card,proposals,state,INK);"
    if old_recompute not in text:
        print("could not patch v38 recompute facit seeding", file=sys.stderr)
        return 2
    text = text.replace(old_recompute, new_recompute, 1)

    text = text.replace("SAOL live-lärande pixelannotering v37", "SAOL live-lärande pixelannotering v38", 1)
    text = text.replace("corrected-v37.json", "corrected-v38.json")
    text = text.replace(
        "<b>Raster först:</b>",
        "<b>Permanent glyphfacit:</b> alla manuellt inlärda unika former från den versionsstyrda facitfilen provas mot varje ord, oberoende av vilka 20 ord som visas. Exakta facitträffar får rösta om stödlinjen; rasterprofilen är startgissning/fallback. <b>Raster först:</b>",
        1,
    )

    args.out.write_text(text, encoding="utf-8")
    print(f"v38: loaded {len(models)} persistent glyph models from {facit}; exact whole-raster seeding + baseline votes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
