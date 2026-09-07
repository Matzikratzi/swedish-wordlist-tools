from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import ocr_manual_pixel_candidate_editor_v8 as v8


def main() -> int:
    """Generate v8 and make bright pixel centres a selected-glyph spotlight.

    All visible annotations keep their normal translucent label colour.  The
    bright centre dot is shown only on pixels belonging to the currently
    selected proposal, so clicking annotation chips behaves like a flashlight
    over the glyph being inspected.
    """
    rc = v8.main()
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

    old = (
        "cells[fy*FW+fx].style.backgroundColor=rgba(colorFor(p.label),alpha);"
        "cells[fy*FW+fx].style.backgroundImage='radial-gradient(circle at center, rgba(255,255,255,.98) 0 2px, rgba(255,255,255,0) 3px)';"
    )
    new = (
        "cells[fy*FW+fx].style.backgroundColor=rgba(colorFor(p.label),alpha);"
        "if(pi===state.selected)cells[fy*FW+fx].style.backgroundImage='radial-gradient(circle at center, rgba(255,255,255,.98) 0 2px, rgba(255,255,255,0) 3px)';"
    )
    if old not in text:
        raise SystemExit("could not patch v9 selected-pixel spotlight")
    text = text.replace(old, new, 1)

    text = text.replace(
        "<h1>SAOL live-lärande pixelannotering v8</h1>",
        "<h1>SAOL live-lärande pixelannotering v9</h1>",
    )
    text = text.replace(
        "Varje markerad pixel har dessutom en ljus centrumprick.",
        "Den valda etiketten fungerar som en ficklampa: bara dess markerade pixlar får ljusa centrumprickar.",
        1,
    )
    text = text.replace("corrected-v8", "corrected-v9")
    text = text.replace("corrected-v8.json", "corrected-v9.json")

    args.out.write_text(text, encoding="utf-8")
    print("v9: bright pixel centres only on the selected annotation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
