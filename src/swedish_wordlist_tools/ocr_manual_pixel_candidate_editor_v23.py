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

    text = out.read_text(encoding="utf-8")

    # Resumed-atlas cards pass through v20 with baselineManual=true. Ordinary
    # matches input (for example a newly prepared next20 batch) never has that
    # frozen state, so there is nothing to reactivate. Both paths are valid.
    frozen = "baselineManual:true,baselineVotes:0"
    active = "baselineManual:false,baselineVotes:0"
    reactivated = False
    if frozen in text:
        text = text.replace(frozen, active)
        reactivated = True

    # baseline_y is the bottom ink row. Draw the visible support line on the
    # lower edge of that raster row, i.e. directly underneath letters that sit
    # on the baseline. This changes presentation only; glyph coordinates stay
    # in source-raster coordinates. Different upstream paths have used both the
    # centre-row and already-lower-edge spelling; accept either.
    old_line = "line.style.top=((state.baseline + MARGIN + 0.5) * SCALE - 1)+'px';"
    new_line = "line.style.top=((state.baseline + MARGIN + 1) * SCALE - 1)+'px';"
    if old_line in text:
        text = text.replace(old_line, new_line, 1)
    elif new_line not in text:
        # Do not make ordinary matches batches unusable merely because their
        # upstream renderer already has another equivalent guide expression.
        print("v23: baseline guide expression already handled upstream")

    text = text.replace(
        "<b>Facitstödlinje:</b> återupptagen atlas använder sparad baseline_y exakt; ingen automatisk omröstning får flytta den. ",
        "<b>Glyph-röstad stödlinje:</b> efter registrering mot svart bläck röstar vanliga baslinjebokstäver om nedersta bläckraden; stödlinjen ritas direkt under den vinnande rasterraden. Din manuella justering vinner därefter alltid. ",
        1,
    )
    text = text.replace(
        "<b>Baslinjekoordinat:</b> på återupptaget facit är sparad baseline_y absolut; den omröstas inte. Stödlinjen ritas genom den rasterrad baseline_y anger och samma värde används för all vertikal glyphmatchning. ",
        "<b>Baslinjekoordinat:</b> baseline_y är nedersta bläckraden för bokstäver som står på raden. Efter registrering röstar facitglypherna fram denna rad, medan den röda stödlinjen visas på radens nederkant. ",
        1,
    )

    text = text.replace("SAOL live-lärande pixelannotering v21", "SAOL live-lärande pixelannotering v23", 1)
    text = text.replace("corrected-v21.json", "corrected-v23.json")
    out.write_text(text, encoding="utf-8")
    mode = "resumed-atlas reactivated" if reactivated else "ordinary matches; no frozen baseline to reactivate"
    print(f"v23: registered glyphs vote for bottom ink row; guide drawn directly underneath ({mode})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
