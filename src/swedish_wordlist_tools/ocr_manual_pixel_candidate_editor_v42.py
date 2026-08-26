from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import ocr_manual_pixel_candidate_editor_v41 as v41


def main() -> int:
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("matches")
    ap.add_argument("library")
    ap.add_argument("--out", type=Path, required=True)
    args, _ = ap.parse_known_args(sys.argv[1:])

    rc = v41.main()
    if rc or not args.out.exists():
        return rc

    text = args.out.read_text(encoding="utf-8")
    anchor = "function rawGlyphSegmentsV41(INK,W,H){"
    if anchor not in text:
        print("could not find v42 helper anchor", file=sys.stderr)
        return 2

    helpers = r'''
function proposalIsPerfectV42(p){
 const missing=Number(p.missing||0),extra=Number(p.extra||0);
 const matched=Number(p.matched ?? (p.pixels ? p.pixels.size : 0));
 const total=Number(p.total ?? (p.pixels ? p.pixels.size : 0));
 return missing===0 && extra===0 && total>0 && matched===total;
}
function overlapCountV42(a,b){
 if(!a||!b)return 0;let n=0;
 const small=a.size<=b.size?a:b,big=a.size<=b.size?b:a;
 for(const k of small)if(big.has(k))n++;
 return n;
}
function fullGlyphStrengthV42(p){
 const n=p.pixels?p.pixels.size:0;
 const perfect=proposalIsPerfectV42(p);
 const miss=Number(p.missing||0),extra=Number(p.extra||0);
 // Coverage is deliberately super-linear. A perfect 40-pixel glyph must beat
 // many 3/4/5/8-pixel fragments that merely happen to occur inside it.
 // Imperfect candidates lose sharply for missing/extra ink.
 let s=n*n;
 if(perfect)s*=8;
 else s*=Math.max(0.05,1-(miss+extra)/Math.max(1,n));
 if(p.facit)s*=1.5;
 if(p.status==='manual')s*=100;
 return s;
}
function enforcePerfectFullGlyphDominanceV42(card,proposals,state,INK){
 const autos=proposals.filter(p=>p.status!=='manual'&&p.pixels&&p.pixels.size&&!p.ignoreSuppressed);
 const perfectLarge=autos.filter(p=>proposalIsPerfectV42(p)&&p.pixels.size>=12)
   .sort((a,b)=>fullGlyphStrengthV42(b)-fullGlyphStrengthV42(a));
 const winners=[];
 for(const p of perfectLarge){
   let blocked=false;
   for(const w of winners){
     const ov=overlapCountV42(p.pixels,w.pixels);
     if(ov && fullGlyphStrengthV42(w)>=fullGlyphStrengthV42(p)){blocked=true;break;}
   }
   if(!blocked)winners.push(p);
 }
 for(const w of winners){
   w.fullGlyphWinnerV42=true;w.suppressed=false;
   const wn=w.pixels.size;
   for(const p of autos){
     if(p===w)continue;
     const ov=overlapCountV42(w.pixels,p.pixels);if(!ov)continue;
     const pn=p.pixels.size;
     const insideFrac=ov/Math.max(1,pn);
     const winnerFrac=ov/Math.max(1,wn);
     // Any much smaller candidate substantially contained in a perfect whole
     // glyph is a fragment explanation and is forbidden, regardless of how
     // many such fragments could otherwise be combined.
     if(pn<wn && insideFrac>=0.55 && fullGlyphStrengthV42(w)>fullGlyphStrengthV42(p)*1.25){
       p.suppressed=true;p.dominatedByFullGlyphV42=true;
     } else if(pn<=10 && insideFrac>0){
       p.suppressed=true;p.dominatedByFullGlyphV42=true;
     }
   }
 }
 // embeddedTiny is a hard veto at the very end. No later overlap resolver may
 // resurrect it.
 for(const p of proposals){if(p.embeddedTiny||p.dominatedByFullGlyphV42)p.suppressed=true;}
 state.fullGlyphWinnersV42=winners.length;
 if(state.render)state.render();
 return winners;
}
'''
    text = text.replace(anchor, helpers + "\n" + anchor, 1)

    old_apply = "rejectEmbeddedTinyV41(card,proposals,state,INK);\n if(typeof resolveCandidateOverlaps==='function')resolveCandidateOverlaps(proposals,INK,W,H,state);\n state.baselineVotes=(r.profile&&r.profile.votes)?r.profile.votes.size:0;"
    new_apply = "rejectEmbeddedTinyV41(card,proposals,state,INK);\n if(typeof resolveCandidateOverlaps==='function')resolveCandidateOverlaps(proposals,INK,W,H,state);\n enforcePerfectFullGlyphDominanceV42(card,proposals,state,INK);\n state.baselineVotes=(r.profile&&r.profile.votes)?r.profile.votes.size:0;"
    if old_apply not in text:
        print("could not patch v42 automatic post-pass", file=sys.stderr)
        return 2
    text = text.replace(old_apply, new_apply, 1)

    old_manual = "if(!state.baselineManual)applyRawBaselineV41(card,proposals,state,INK);else rejectEmbeddedTinyV41(card,proposals,state,INK);"
    new_manual = "if(!state.baselineManual)applyRawBaselineV41(card,proposals,state,INK);else {rejectEmbeddedTinyV41(card,proposals,state,INK);enforcePerfectFullGlyphDominanceV42(card,proposals,state,INK);}"
    if old_manual not in text:
        print("could not patch v42 manual-baseline post-pass", file=sys.stderr)
        return 2
    text = text.replace(old_manual, new_manual, 1)

    old_re = "let ob=null;if(!state.baselineManual)ob=applyRawBaselineV41(card,proposals,state,INK);else rejectEmbeddedTinyV41(card,proposals,state,INK);"
    new_re = "let ob=null;if(!state.baselineManual)ob=applyRawBaselineV41(card,proposals,state,INK);else {rejectEmbeddedTinyV41(card,proposals,state,INK);enforcePerfectFullGlyphDominanceV42(card,proposals,state,INK);}"
    if old_re in text:
        text = text.replace(old_re, new_re, 1)

    text = text.replace("SAOL live-lärande pixelannotering v41", "SAOL live-lärande pixelannotering v42", 1)
    text = text.replace("corrected-v41.json", "corrected-v42.json")
    text = text.replace(
        "<b>Råglyph-baslinje v41:</b>",
        "<b>Helglyph-dominans v42:</b> en stor perfekt glyph får superlinjär täckningspoäng och slår alltid en mosaik av mindre delträffar. 100 % täckning utan extra bläck premieras mycket kraftigt; saknade/extra pixlar straffas. Små kandidater som ligger inne i en perfekt helglyph underkänns slutgiltigt. <b>Råglyph-baslinje v41:</b>",
        1,
    )

    args.out.write_text(text, encoding="utf-8")
    print("v42: perfect full-glyph dominance; large exact glyphs beat fragment mosaics; embedded-tiny veto is final")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
