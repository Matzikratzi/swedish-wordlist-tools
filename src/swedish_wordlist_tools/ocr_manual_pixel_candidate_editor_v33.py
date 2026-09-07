from __future__ import annotations

import re
import sys
from pathlib import Path

from . import ocr_manual_pixel_candidate_editor_v32 as v32


def main() -> int:
    argv = sys.argv[1:]
    out: Path | None = None
    if "--out" in argv:
        i = argv.index("--out")
        if i + 1 < len(argv):
            out = Path(argv[i + 1])

    rc = v32.main()
    if rc or out is None or not out.exists():
        return rc

    text = out.read_text(encoding="utf-8")

    # Plain python -m http.server answers POST with 501, not 404.  Treat both as
    # "no save API" so local download remains the normal path without a warning.
    old = "if(response.status===404){saveMessage='Serversparning saknas på denna webbserver · lokal fil laddas ned';}"
    new = "if(response.status===404 || response.status===501){saveMessage='Serversparning saknas på denna webbserver · lokal fil laddas ned';}"
    if old not in text:
        print("could not patch v33 local-only server save status", file=sys.stderr)
        return 2
    text = text.replace(old, new, 1)

    # Exact full-shape matches should dominate tiny partial glyphs.  Reward a
    # candidate that has no missing/extra pixels and explains its complete model;
    # penalise the inverse situation where only a small fraction of nearby ink is
    # covered by the candidate.  This is intentionally strong for cases such as
    # four half-lod templates sitting inside one exact bold 'l'.
    old_weight = "const rel=relativeGlyphScore(p);return p.pixels.size + 0.45*quality + 8*rel - (Number.isFinite(+p.lod_distance_error)?6*Math.abs(+p.lod_distance_error):0);"
    new_weight = "const rel=relativeGlyphScore(p);const exact=(+p.missing||0)===0 && (+p.extra||0)===0 && (!Number.isFinite(+p.total) || (+p.matched||p.pixels.size)>=(+p.total||p.pixels.size));const exactBonus=exact?Math.max(12,0.8*p.pixels.size):0;const bbox=proposalBounds(p);let localInk=0;if(bbox){for(let y=bbox.ymin;y<=bbox.ymax;y++)for(let x=bbox.xmin;x<=bbox.xmax;x++)if(INK[y]&&INK[y][x])localInk++;}const coverage=localInk?Math.min(1,p.pixels.size/localInk):1;const partialPenalty=(1-coverage)*10;return p.pixels.size + 0.45*quality + 8*rel + exactBonus - partialPenalty - (Number.isFinite(+p.lod_distance_error)?6*Math.abs(+p.lod_distance_error):0);"
    if old_weight not in text:
        print("could not patch v33 exact-match weighting", file=sys.stderr)
        return 2
    text = text.replace(old_weight, new_weight, 1)

    # Surface exactness/coverage while tuning.
    old_display = "+p.label+' ['+proposalStyle(p,card)+'] · '+p.status+' · '+p.pixels.size+' px'+(Number.isFinite(p.relative_score)?' · '+Math.round(100*p.relative_score)+'%':'')+(Number.isFinite(p.lod_distance_error)?' · lod Δ'+p.lod_distance_error:'')"
    new_display = "+p.label+' ['+proposalStyle(p,card)+'] · '+p.status+' · '+p.pixels.size+' px'+(Number.isFinite(p.relative_score)?' · '+Math.round(100*p.relative_score)+'%':'')+(((+p.missing||0)===0&&(+p.extra||0)===0)?' · exakt':'')+(Number.isFinite(p.lod_distance_error)?' · lod Δ'+p.lod_distance_error:'')"
    if old_display in text:
        text = text.replace(old_display, new_display, 1)

    text = text.replace("SAOL live-lärande pixelannotering v32", "SAOL live-lärande pixelannotering v33", 1)
    text = text.replace("corrected-v32.json", "corrected-v33.json")
    text = text.replace(
        "<b>Räkna om ordet:</b>",
        "<b>Exakt helglyph prioriteras:</b> en kandidat utan missing/extra får en kraftig bonus, särskilt när den täcker en hel större glyph. Små mallar som bara förklarar en del av samma bläck får därför inte vinna genom att staplas. <b>Räkna om ordet:</b>",
        1,
    )
    out.write_text(text, encoding="utf-8")
    print("v33: exact full-glyph matches strongly preferred; plain http.server 501 treated as local-only export")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
