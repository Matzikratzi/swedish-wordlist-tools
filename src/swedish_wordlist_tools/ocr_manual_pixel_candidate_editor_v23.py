from __future__ import annotations

import sys
from pathlib import Path

from . import ocr_manual_pixel_candidate_editor_v22 as v22


def main() -> int:
    argv = sys.argv[1:]
    out: Path | None = None
    if "--out" in argv:
        i = argv.index("--out")
        if i + 1 < len(argv):
            out = Path(argv[i + 1])

    rc = v22.main()
    if rc or out is None or not out.exists():
        return rc

    text = out.read_text(encoding="utf-8")

    # v20 froze resumed-atlas baselines. After v21 source-ink registration that
    # is no longer desirable: registered manual glyphs are aligned to the actual
    # black raster and can safely vote for the baseline again. The vote stores
    # the bottom ink row (max y); v22 draws the guide on that row's lower edge,
    # i.e. directly underneath ordinary baseline letters such as a/b/c/d/e/o.
    frozen = "baselineManual:true,baselineVotes:0"
    active = "baselineManual:false,baselineVotes:0"
    if frozen not in text:
        print("could not reactivate v23 baseline voting", file=sys.stderr)
        return 2
    text = text.replace(frozen, active)

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

    text = text.replace("pixeleditor-bold-v22", "pixeleditor-bold-v23")
    text = text.replace("corrected-v22.json", "corrected-v23.json")
    text = text.replace("v22: baseline display is half a raster pixel lower", "v22: baseline display is half a raster pixel lower; v23: registered glyphs vote for the bottom ink row")
    out.write_text(text, encoding="utf-8")
    print("v23: source-registered glyphs vote for baseline bottom row; guide is drawn directly underneath")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
