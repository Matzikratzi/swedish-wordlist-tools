from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from .ocr_find_unreviewed_glyph_rows import _available_pages, _selected_pages
from .ocr_review_page_pixel_array_glyphs_html import build_page_context_pixel_array


def _owned_row_points(context: dict, column_index: int, row_index: int) -> set[tuple[int, int]]:
    column = context["row_map"]["columns"][column_index]
    rows = column.get("rows") or []
    row = rows[row_index]
    owners = context["pixel_owners"]
    left = max(0, int(row.get("crop_left", column.get("crop_left", column.get("left", 0)))))
    right = min(owners.width, int(row.get("crop_right", column.get("crop_right", column.get("right", owners.width)))))
    top = max(0, int(row["page_top"]) if row_index == 0 else int(rows[row_index - 1]["page_bottom"]))
    bottom = min(owners.height, int(row["page_bottom"]))
    return owners.owner_ink_points(
        row_index=row_index,
        left=left,
        top=top,
        right=right,
        bottom=bottom,
    )


def _left_profile(points: set[tuple[int, int]]) -> list[tuple[int, int]]:
    by_y: dict[int, int] = {}
    for x, y in points:
        previous = by_y.get(y)
        if previous is None or x < previous:
            by_y[y] = x
    return sorted(by_y.items())


def _record_left_jumps(profile: list[tuple[int, int]]) -> list[tuple[int, int, int, int]]:
    """Return (ink_row_number, page_y, old_x, jump_left) for new left records."""
    if not profile:
        return []
    record_x = profile[0][1]
    out: list[tuple[int, int, int, int]] = []
    for ink_row_number, (y, x) in enumerate(profile[1:], start=2):
        if x >= record_x:
            continue
        old_x = record_x
        record_x = x
        out.append((ink_row_number, y, old_x, old_x - x))
    return out


def _quantile(sorted_values: list[int], q: float) -> int | None:
    if not sorted_values:
        return None
    index = round((len(sorted_values) - 1) * q)
    return sorted_values[max(0, min(len(sorted_values) - 1, index))]


def _fmt_distribution(counter: Counter[int], *, limit: int = 30) -> str:
    rows = sorted(counter.items())
    if len(rows) > limit:
        rows = rows[:limit]
    return " ".join(f"{value}:{count}" for value, count in rows)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Measure physical/ink row heights and how the leftmost source pixel "
            "moves left as more ink-bearing raster rows are observed."
        )
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--start-page", type=int, default=1)
    ap.add_argument("--end-page", type=int, default=10)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument(
        "--watch-ink-rows",
        type=int,
        default=4,
        help="report left-record jumps that occur after this many ink-bearing raster rows",
    )
    ap.add_argument(
        "--top",
        type=int,
        default=20,
        help="show this many largest leftward record jumps",
    )
    args = ap.parse_args()
    if args.watch_ink_rows < 1:
        raise ValueError("--watch-ink-rows must be >= 1")

    pages = _selected_pages(
        _available_pages(args.jsonl),
        pages=None,
        start_page=args.start_page,
        end_page=args.end_page,
    )
    if not pages:
        raise ValueError("no pages selected")

    physical_heights: list[int] = []
    ink_heights: list[int] = []
    ink_row_counts: list[int] = []
    jump_sizes: list[int] = []
    jump_depths: list[int] = []
    jumps_after_watch: list[tuple[int, int, int, int, int, int, list[tuple[int, int]]]] = []
    all_jumps: list[tuple[int, int, int, int, int, int, list[tuple[int, int]]]] = []
    rows_scanned = 0

    for page in pages:
        context = build_page_context_pixel_array(args.jsonl, page, args.threshold)
        context["quiet_successful_ownership"] = True
        for column_index, column in enumerate(context["row_map"].get("columns") or []):
            rows = column.get("rows") or []
            for row_index, row in enumerate(rows):
                rows_scanned += 1
                physical_heights.append(int(row["page_bottom"]) - int(row["page_top"]))
                points = _owned_row_points(context, column_index, row_index)
                profile = _left_profile(points)
                if not profile:
                    continue
                ink_heights.append(profile[-1][0] - profile[0][0] + 1)
                ink_row_counts.append(len(profile))
                for ink_row_number, _y, old_x, jump in _record_left_jumps(profile):
                    jump_sizes.append(jump)
                    jump_depths.append(ink_row_number)
                    item = (
                        jump,
                        ink_row_number,
                        page,
                        column_index,
                        row_index,
                        old_x,
                        profile,
                    )
                    all_jumps.append(item)
                    if ink_row_number > args.watch_ink_rows:
                        jumps_after_watch.append(item)

    def report_values(name: str, values: list[int]) -> None:
        ordered = sorted(values)
        print(
            f"{name}: n={len(values)} min={ordered[0] if ordered else '-'} "
            f"p01={_quantile(ordered, 0.01)} p05={_quantile(ordered, 0.05)} "
            f"p50={_quantile(ordered, 0.50)} p95={_quantile(ordered, 0.95)} "
            f"p99={_quantile(ordered, 0.99)} max={ordered[-1] if ordered else '-'}"
        )
        print(f"{name}-distribution: {_fmt_distribution(Counter(values))}")

    print(f"summary: pages={len(pages)} ({pages[0]}..{pages[-1]}) rows={rows_scanned}")
    report_values("physical-height", physical_heights)
    report_values("ink-height", ink_heights)
    report_values("ink-bearing-rows", ink_row_counts)
    report_values("left-record-jump", jump_sizes)
    report_values("left-record-depth", jump_depths)

    print(
        f"after-{args.watch_ink_rows}-ink-rows: jumps={len(jumps_after_watch)} "
        f"rows-with-jump={len({(p, c, r) for _j, _d, p, c, r, _x, _prof in jumps_after_watch})}"
    )
    after_sizes = [item[0] for item in jumps_after_watch]
    if after_sizes:
        report_values(f"after-{args.watch_ink_rows}-jump", after_sizes)

    print(f"largest-left-record-jumps: top={args.top}")
    for rank, item in enumerate(sorted(all_jumps, reverse=True)[: args.top], start=1):
        jump, depth, page, column, row, old_x, profile = item
        new_x = old_x - jump
        profile_text = " ".join(f"y{y}:x{x}" for y, x in profile)
        print(
            f"jump rank={rank} jump={jump} depth={depth} page={page} column={column} row={row} "
            f"x={old_x}->{new_x} profile={profile_text}"
        )

    print(f"largest-jumps-after-{args.watch_ink_rows}: top={args.top}")
    for rank, item in enumerate(sorted(jumps_after_watch, reverse=True)[: args.top], start=1):
        jump, depth, page, column, row, old_x, profile = item
        new_x = old_x - jump
        profile_text = " ".join(f"y{y}:x{x}" for y, x in profile)
        print(
            f"late-jump rank={rank} jump={jump} depth={depth} page={page} column={column} row={row} "
            f"x={old_x}->{new_x} profile={profile_text}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
