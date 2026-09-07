from __future__ import annotations

import argparse
import json
from pathlib import Path

from .ocr_glyph_review_delete import load_facit_with_typography, mark_matches_reviewed
from .ocr_review_page_pixel_array_glyphs_html import (
    build_page_context_pixel_array,
    load_review_state_pixel_array,
)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Mark every glyph model encountered from row 0 through a trusted row as reviewed, "
            "and mark all other facit models as needing review."
        )
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--page", type=int, required=True)
    ap.add_argument("--column", type=int, choices=(0, 1, 2), required=True)
    ap.add_argument("--through-row", type=int, required=True)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--facit", type=Path, required=True)
    args = ap.parse_args()

    context = build_page_context_pixel_array(args.jsonl, args.page, args.threshold)
    positions = set(context["positions"])
    wanted = [(args.column, row) for row in range(args.through_row + 1)]
    missing = [position for position in wanted if position not in positions]
    if missing:
        raise ValueError(f"rows are not present on page: {missing}")

    models = load_facit_with_typography(args.facit)
    matches = []
    for position in wanted:
        state = load_review_state_pixel_array(context, position, models)
        matches.extend(state.get("matches") or [])
        print(
            f"review-seed: c{position[0]} r{position[1]} "
            f"{state['covered_pixels']}/{state['source_pixels']} px, "
            f"{len(state.get('matches') or [])} matchade glypher",
            flush=True,
        )

    payload = json.loads(args.facit.read_text(encoding="utf-8"))
    mark_matches_reviewed(payload, matches, reset=True)
    args.facit.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    reviewed = sum(bool(glyph.get("reviewed", False)) for glyph in payload.get("glyphs") or [])
    total = len(payload.get("glyphs") or [])
    print(
        f"review-seed: {reviewed}/{total} facitmallar markerade kontrollerade; "
        f"övriga {total - reviewed} kräver granskning"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
