from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from .ocr_glyph_matcher import load_facit
from .ocr_left_edge_index import LeftEdgeIndex, derived_baseline
from .ocr_left_edge_source_walk import source_walk_hits_with_top_retry
from .ocr_prepare_sequential_page import _load_source_image, read_jsonl, source_for_page


@dataclass(frozen=True)
class Case:
    name: str
    page: int
    column: int
    row: int
    crop: tuple[int, int, int, int]
    current_anchor_x: int
    current_text: str


CASES = (
    Case("2a", 39, 0, 26, (2, 535, 255, 548), 85, "."),
    Case("2b", 39, 2, 2, (458, 114, 698, 132), 71, ","),
    Case("2c", 50, 2, 12, (456, 291, 698, 312), 72, "-"),
    Case("2d", 64, 0, 43, (0, 838, 249, 861), 147, "--"),
    Case("2e", 75, 0, 24, (2, 503, 250, 522), 94, "-"),
)


def _black_points(image, *, threshold: int) -> set[tuple[int, int]]:
    gray = image.convert("L")
    return {
        (x, y)
        for y in range(gray.height)
        for x in range(gray.width)
        if gray.getpixel((x, y)) < threshold
    }


def run_case(jsonl: Path, facit: Path, case: Case, *, threshold: int, limit: int) -> None:
    source = source_for_page(read_jsonl(jsonl), case.page)
    if not source:
        raise ValueError(f"no source found for page {case.page}")
    page = _load_source_image(source)
    if page is None:
        raise ValueError(f"could not load page image: {source}")

    crop = page.crop(case.crop)
    black = _black_points(crop, threshold=threshold)
    index = LeftEdgeIndex(load_facit(facit))
    hits = source_walk_hits_with_top_retry(
        black,
        index,
        max_x=case.current_anchor_x,
        max_depth=16,
        max_skip_rows=8,
    )

    print(
        f"case #{case.name}: page={case.page} column={case.column} row={case.row} "
        f"crop={case.crop} ink={len(black)} current_anchor_x={case.current_anchor_x} "
        f"current={case.current_text!r}"
    )
    if not hits:
        print("  source walk found no exact glyph at or before current anchor after top-row retry")
        return

    leftmost = min(hit.x for hit in hits)
    skipped = min(hit.skipped_top_rows for hit in hits)
    print(
        f"  source-walk hits={len(hits)} skipped_top_rows={skipped} "
        f"leftmost_x={leftmost} delta_to_current={case.current_anchor_x-leftmost}"
    )

    shown = 0
    for hit in sorted(
        hits,
        key=lambda item: (
            item.x,
            item.y,
            -max(len(glyph.model.pixels) for glyph in item.exact),
            len(item.candidates),
        ),
    ):
        for glyph in sorted(
            hit.exact,
            key=lambda item: (-len(item.model.pixels), item.model.label, item.model.style),
        ):
            if shown >= limit:
                return
            model = glyph.model
            baseline = derived_baseline(glyph, source_top_y=hit.y)
            marker = "LEFTMOST" if hit.x == leftmost else ""
            prefix_text = "[" + ",".join(
                "." if value is None else str(value) for value in hit.prefix
            ) + "]"
            print(
                f"  x={hit.x:>3} y={hit.y:>2} skip={hit.skipped_top_rows:>2} "
                f"page=({case.crop[0]+hit.x},{case.crop[1]+hit.y}) "
                f"glyph={model.label!r}/{model.style} px={len(model.pixels):>3} "
                f"prefix_len={len(hit.prefix):>2} candidates={len(hit.candidates):>3} "
                f"baseline_local={baseline:>2} baseline_page={case.crop[1]+baseline} "
                f"prefix={prefix_text} {marker}".rstrip()
            )
            shown += 1


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Walk source left contours without a baseline on the collected #2 "
            "anchor-failure rows, retrying below top ink when a later tall glyph "
            "may protrude above a low first glyph."
        )
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument(
        "--facit",
        type=Path,
        default=Path("glyphs/saol14-manual-glyph-facit-v2.json"),
    )
    ap.add_argument("--case", choices=[case.name for case in CASES], action="append")
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--limit", type=int, default=20)
    args = ap.parse_args()

    selected = CASES if not args.case else tuple(case for case in CASES if case.name in args.case)
    for n, case in enumerate(selected):
        if n:
            print()
        run_case(args.jsonl, args.facit, case, threshold=args.threshold, limit=args.limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
