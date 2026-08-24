from __future__ import annotations

import sys
from pathlib import Path

from . import ocr_manual_pixel_candidate_editor_v21 as v21


def main() -> int:
    argv = sys.argv[1:]
    out: Path | None = None
    if "--out" in argv:
        i = argv.index("--out")
        if i + 1 < len(argv):
            out = Path(argv[i + 1])

    rc = v21.main()
    if rc or out is None or not out.exists():
        return rc

    html = out.read_text(encoding="utf-8")

    # v20/v21 place the baseline through the centre of the baseline raster
    # row.  For visual review we want the conventional baseline at the lower
    # edge of that raster row.  This is display-only: baseline_y, annotation
    # coordinates and matching are deliberately left untouched.
    needle = "top:${margin + (baselineY + 0.5) * scale}px"
    replacement = "top:${margin + (baselineY + 1.0) * scale}px"
    if needle in html:
        html = html.replace(needle, replacement)
    else:
        # Keep this version useful even if the exact v20 patch spelling
        # changes: patch the known half-raster expression once.
        needle2 = "(baselineY + 0.5) * scale"
        if needle2 not in html:
            print("could not adjust v22 baseline display", file=sys.stderr)
            return 2
        html = html.replace(needle2, "(baselineY + 1.0) * scale", 1)

    html = html.replace(
        "v21: source-ink registration aligns resumed atlas annotations before editing",
        "v21: source-ink registration aligns resumed atlas annotations before editing; v22: baseline display is half a raster pixel lower",
        1,
    )
    out.write_text(html, encoding="utf-8")
    print("v22: baseline display moved half a raster pixel down; data coordinates unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
