from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import ocr_manual_pixel_candidate_editor_v19 as v19


def _is_atlas(path: Path) -> bool:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(payload, dict) or not isinstance(payload.get("words"), list):
        return False
    fmt = str(payload.get("format") or "")
    return fmt.startswith("saol-manual-pixel-atlas-corrected-") or fmt.startswith("saol-manual-pixel-atlas-merged-")


def main() -> int:
    original_argv = sys.argv[:]
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("matches", type=Path)
    ap.add_argument("library")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--scale")
    ap.add_argument("--margin")
    ap.add_argument("--ink-threshold")
    ap.add_argument("--examples-per-char")
    args, _ = ap.parse_known_args(sys.argv[1:])
    resumed = _is_atlas(args.matches)

    rc = v19.main()
    sys.argv = original_argv
    if rc:
        return rc

    text = args.out.read_text(encoding="utf-8")

    if resumed:
        # A resumed atlas already contains a human-reviewed baseline_y. v10's
        # glyph voting must never move it: that would also shift every propagated
        # glyph because propagation is baseline-relative.
        old_state = "baselineManual:false,baselineVotes:0"
        new_state = "baselineManual:true,baselineVotes:0"
        if old_state not in text:
            raise SystemExit("could not freeze resumed atlas baseline")
        text = text.replace(old_state, new_state)

        # Remove any explanatory text suggesting that voting is active for these
        # cards. The stored baseline is the authority on resumed atlas input.
        text = text.replace(
            "<b>Glyph-röstad stödlinje:</b> vanliga bokstäver som står på raden röstar om stödlinjens y-läge; din manuella justering vinner alltid. ",
            "<b>Facitstödlinje:</b> återupptagen atlas använder sparad baseline_y exakt; ingen automatisk omröstning får flytta den. ",
            1,
        )

    # baseline_y denotes the raster row whose ink sits on the baseline. Draw the
    # guide through that row (at its vertical centre), rather than on the lower
    # border after it, which visually looked one source pixel too low.
    old_line = "line.style.top=((state.baseline + MARGIN + 1) * SCALE - 1)+'px';"
    new_line = "line.style.top=((state.baseline + MARGIN + 0.5) * SCALE - 1)+'px';"
    if old_line not in text:
        raise SystemExit("could not reposition v20 baseline guide")
    text = text.replace(old_line, new_line, 1)

    text = text.replace("SAOL live-lärande pixelannotering v19", "SAOL live-lärande pixelannotering v20", 1)
    text = text.replace("corrected-v19.json", "corrected-v20.json")
    text = text.replace(
        "<p><b>Pixelvisning:</b>",
        "<p><b>Baslinjekoordinat:</b> på återupptaget facit är sparad baseline_y absolut; den omröstas inte. Stödlinjen ritas genom den rasterrad baseline_y anger och samma värde används för all vertikal glyphmatchning. <b>Pixelvisning:</b>",
        1,
    )

    args.out.write_text(text, encoding="utf-8")
    print(f"v20: stored baseline authoritative={resumed}; guide drawn through baseline raster row")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
