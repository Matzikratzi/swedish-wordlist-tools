from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import ocr_manual_pixel_candidate_editor_v18 as v18


def main() -> int:
    """Generate v18 and make annotations preserve visible source ink.

    v19 changes presentation only:
    * annotated raster cells are no longer filled with translucent colour;
    * colour occupies the lower-right diagonal half of the same pixel cell,
      leaving the upper-left half transparent so the black facsimile pixel is
      always directly visible;
    * the baseline remains an independent overlay at the lower edge of the
      source raster row designated by baseline_y.
    """
    rc = v18.main()
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

    # All editor generations clear annotation paint before every render.  Clear
    # both colour and image so old full-cell fills cannot survive a redraw.
    old_clear = "for(let i=0;i<cells.length;i++){cells[i].style.backgroundColor='';cells[i].style.backgroundImage='';}"
    if old_clear not in text:
        old_clear = "for(let i=0;i<cells.length;i++)cells[i].style.backgroundColor='';"
    new_clear = "for(let i=0;i<cells.length;i++){cells[i].style.backgroundColor='transparent';cells[i].style.backgroundImage='';}"
    if old_clear not in text:
        raise SystemExit("could not patch v19 annotation clearing")
    text = text.replace(old_clear, new_clear, 1)

    # Replace the actual annotation paint.  The diagonal is intentionally in the
    # same DOM cell as the source pixel: no x/y offset and no shadow layer.  The
    # transparent half exposes the original black raster underneath.
    paint_variants = [
        "cells[fy*FW+fx].style.backgroundColor=rgba(colorFor(p.label),alpha);if(pi===state.selected)cells[fy*FW+fx].style.backgroundImage='radial-gradient(circle at center, rgba(255,255,255,.98) 0 2px, rgba(255,255,255,0) 3px)';",
        "cells[fy*FW+fx].style.backgroundColor=rgba(colorFor(p.label),alpha);cells[fy*FW+fx].style.backgroundImage='radial-gradient(circle at center, rgba(255,255,255,.98) 0 2px, rgba(255,255,255,0) 3px)';",
        "cells[fy*FW+fx].style.backgroundColor=rgba(colorFor(p.label),alpha);",
    ]
    paint = next((p for p in paint_variants if p in text), None)
    if paint is None:
        raise SystemExit("could not patch v19 annotation painting")
    diagonal = (
        "cells[fy*FW+fx].style.backgroundColor='transparent';"
        "cells[fy*FW+fx].style.backgroundImage="
        "'linear-gradient(135deg, transparent 0 49%, '+rgba(colorFor(p.label),Math.min(.82,alpha+.24))+' 50% 100%)';"
    )
    text = text.replace(paint, diagonal, 1)

    # Make the baseline definition explicit. baseline_y is a source-raster row;
    # the line belongs on that row's lower edge after the display margin.
    old_line = "line.style.top=((state.baseline+MARGIN+1)*SCALE-1)+'px';"
    new_line = "line.style.top=((state.baseline + MARGIN + 1) * SCALE - 1)+'px';"
    if old_line in text:
        text = text.replace(old_line, new_line, 1)

    # Keep the source image visually strong; annotation cells are now mostly
    # transparent and only the diagonal colour overlays it.
    text = text.replace(
        ".stack img{position:absolute;left:0;top:0;display:block;image-rendering:pixelated;z-index:1;pointer-events:none}",
        ".stack img{position:absolute;left:0;top:0;display:block;image-rendering:pixelated;z-index:1;pointer-events:none;opacity:1}",
        1,
    )

    text = text.replace("SAOL live-lärande pixelannotering v18", "SAOL live-lärande pixelannotering v19", 1)
    text = text.replace("corrected-v18.json", "corrected-v19.json")
    text = text.replace(
        "<p><b>Återupptagen atlas:</b>",
        "<p><b>Pixelvisning:</b> annotationens färg ligger bara i pixelrutans nedre diagonal; den andra halvan är transparent så originalets svarta bläck alltid syns utan färgad skugga. Stödlinjen ritas separat på nederkanten av den rasterrad som baseline_y anger. <b>Återupptagen atlas:</b>",
        1,
    )

    args.out.write_text(text, encoding="utf-8")
    print("v19: diagonal annotation markers; source ink remains visible; baseline uses source raster row")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
