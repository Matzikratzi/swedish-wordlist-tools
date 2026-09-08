from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from .ocr_glyph_matcher import load_facit
from .ocr_group_baseline_fallback import _select_at_baseline
from .ocr_left_edge_index import LeftEdgeIndex, derived_baseline
from .ocr_left_edge_source_walk import is_strong_anchor, source_walk_hits_with_resync
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


def _covered(selected) -> set[tuple[int, int]]:
    return set().union(*(match.pixels for match in selected)) if selected else set()


def _selected_text(selected) -> str:
    return "".join(match.label for match in sorted(selected, key=lambda m: (m.x, m.baseline, m.label, m.style)))


def _probe_anchor_baselines(black, crop, models, hits) -> None:
    baseline_sources: dict[int, list[str]] = {}
    for hit in hits:
        if not is_strong_anchor(hit):
            continue
        for glyph in hit.exact:
            baseline = derived_baseline(glyph, source_top_y=hit.y)
            baseline_sources.setdefault(baseline, []).append(
                f"{glyph.model.label!r}/{glyph.model.style}:{glyph.variant}@x{hit.x}"
            )

    if not baseline_sources:
        print("  baseline-probe: no strong contour anchor")
        return

    rows = []
    for baseline, sources in sorted(baseline_sources.items()):
        selected = _select_at_baseline(black, crop.width, crop.height, models, baseline)
        covered = _covered(selected)
        rows.append((len(covered), baseline, selected, sources))

    rows.sort(key=lambda row: (-row[0], row[1]))
    for rank, (covered_pixels, baseline, selected, sources) in enumerate(rows, 1):
        text = _selected_text(selected)
        fully_exact = bool(black) and covered_pixels == len(black)
        print(
            f"  baseline-probe rank={rank} baseline={baseline} "
            f"coverage={covered_pixels}/{len(black)} fully_exact={fully_exact} "
            f"selected={len(selected)} text={text!r} "
            f"anchors={';'.join(sources)}"
        )


def run_case(jsonl: Path, facit: Path, case: Case, *, threshold: int, limit: int) -> None:
    source = source_for_page(read_jsonl(jsonl), case.page)
    if not source:
        raise ValueError(f"no source found for page {case.page}")
    page = _load_source_image(source)
    if page is None:
        raise ValueError(f"could not load page image: {source}")

    crop = page.crop(case.crop)
    black = _black_points(crop, threshold=threshold)
    models = load_facit(facit)
    index = LeftEdgeIndex(models)
    hits = source_walk_hits_with_resync(
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
        print("  source walk found no exact glyph at/before current anchor after x/y resync")
        return

    strong = any(is_strong_anchor(hit) for hit in hits)
    quality = "STRONG" if strong else "WEAK-FALLBACK"
    leftmost = min(hit.x for hit in hits)
    skipped_top = min(hit.skipped_top_rows for hit in hits)
    skipped_left = min(hit.skipped_left_columns for hit in hits)
    print(
        f"  source-walk hits={len(hits)} quality={quality} "
        f"skipped_left_columns={skipped_left} skipped_top_rows={skipped_top} "
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
        hit_quality = "STRONG" if is_strong_anchor(hit) else "WEAK"
        for glyph in sorted(
            hit.exact,
            key=lambda item: (-len(item.model.pixels), item.model.label, item.model.style, item.variant),
        ):
            if shown >= limit:
                break
            model = glyph.model
            baseline = derived_baseline(glyph, source_top_y=hit.y)
            marker = "LEFTMOST" if hit.x == leftmost else ""
            prefix_text = "[" + ",".join(
                "." if value is None else str(value) for value in hit.prefix
            ) + "]"
            print(
                f"  x={hit.x:>3} y={hit.y:>2} quality={hit_quality} "
                f"skipx={hit.skipped_left_columns:>3} skipy={hit.skipped_top_rows:>2} "
                f"page=({case.crop[0]+hit.x},{case.crop[1]+hit.y}) "
                f"glyph={model.label!r}/{model.style} variant={glyph.variant} "
                f"px={len(model.pixels):>3} prefix_len={len(hit.prefix):>2} "
                f"candidates={len(hit.candidates):>3} baseline_local={baseline:>2} "
                f"baseline_page={case.crop[1]+baseline} prefix={prefix_text} {marker}".rstrip()
            )
            shown += 1
        if shown >= limit:
            break

    _probe_anchor_baselines(black, crop, models, hits)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Walk source left contours without a baseline on the collected #2 "
            "anchor-failure rows, resynchronizing both downward and rightward, "
            "then probe the existing baseline-constrained selector from strong anchors."
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