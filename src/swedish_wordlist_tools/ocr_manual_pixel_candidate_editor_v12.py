from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import ocr_manual_pixel_candidate_editor_v11 as v11


def main() -> int:
    """Generate v11 and add bold as an independent per-card style class."""
    rc = v11.main()
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
        '<option value="italic">kursiv</option>'
        '<option value="roman">roman</option>'
    )
    new = (
        '<option value="italic">kursiv</option>'
        '<option value="roman">roman</option>'
        '<option value="bold">fet</option>'
    )
    if old not in text:
        raise SystemExit("could not patch v12 bold style option")
    text = text.replace(old, new)

    text = text.replace(
        "<h1>SAOL live-lärande pixelannotering v11</h1>",
        "<h1>SAOL live-lärande pixelannotering v12</h1>",
    )
    text = text.replace(
        "matcherens roman/kursiv-gissning är bara startvärde.",
        "matcherens kursiv/roman/fet-gissning är bara startvärde. Fet behandlas som en egen glyphklass och delar inte automatiskt facit med roman.",
        1,
    )
    text = text.replace("corrected-v11", "corrected-v12")
    text = text.replace("corrected-v11.json", "corrected-v12.json")

    args.out.write_text(text, encoding="utf-8")
    print("v12: per-card italic/roman/bold style selector")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
