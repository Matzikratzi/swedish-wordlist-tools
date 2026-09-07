from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from .ocr_glyph_matcher import load_facit
from .ocr_left_edge_index import LeftEdgeIndex, derived_baseline, exact_model_at
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


def exact_matches(
    black: set[tuple[int, int]],
    index: LeftEdgeIndex,
    *,
    max_x: int | None = None,
) -> list[tuple[int, int, object]]:
    """Find exact glyph rasters without assuming a baseline.

    Every source ink pixel is tried as the top-row leftmost glyph pixel.  This is
    diagnostic code, so it intentionally favors transparency over speed.  The
    production experiment can later replace the broad model loop with prefix
    lookups from ``LeftEdgeIndex``.
    """
    matches: list[tuple[int, int, object]] = []
    for x, y in sorted(black, key=lambda point: (point[0], point[1])):
        if max_x is not None and x > max_x:
            continue
        for glyph in index.glyphs:
            if exact_model_at(black, glyph, x=x, y=y):
                matches.append((x, y, glyph))
    matches.sort(
        key=lambda item: (
            item[0],
            item[1],
            -len(item[2].model.pixels),
            item[2].model.label,
            item[2].model.style,
        )
    )
    return matches


def _candidate_counts(index: LeftEdgeIndex, glyph) -> str:
    parts = []
    for depth in (4, 8, 12):
        prefix = glyph.signature[:depth]
        parts.append(f"d{depth}={len(index.candidates(prefix))}")
    return " ".join(parts)


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
    before_or_at_anchor = exact_matches(black, index, max_x=case.current_anchor_x)

    print(
        f"case #{case.name}: page={case.page} column={case.column} row={case.row} "
        f"crop={case.crop} ink={len(black)} current_anchor_x={case.current_anchor_x} "
        f"current={case.current_text!r}"
    )
    if not before_or_at_anchor:
        print("  no exact glyph model found at or before current anchor")
        return

    leftmost = before_or_at_anchor[0][0]
    print(
        f"  exact matches at/before current anchor={len(before_or_at_anchor)} "
        f"leftmost_x={leftmost} delta_to_current={case.current_anchor_x-leftmost}"
    )
    shown = 0
    for x, y, glyph in before_or_at_anchor:
        if shown >= limit:
            break
        model = glyph.model
        page_x = case.crop[0] + x
        page_y = case.crop[1] + y
        baseline = derived_baseline(glyph, source_top_y=y)
        marker = "LEFTMOST" if x == leftmost else ""
        print(
            f"  x={x:>3} y={y:>2} page=({page_x},{page_y}) "
            f"glyph={model.label!r}/{model.style} px={len(model.pixels):>3} "
            f"baseline_local={baseline:>2} baseline_page={case.crop[1]+baseline} "
            f"{_candidate_counts(index, glyph)} {marker}".rstrip()
        )
        shown += 1


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Try baseline-free exact glyph starts on the collected #2 failure rows."
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
