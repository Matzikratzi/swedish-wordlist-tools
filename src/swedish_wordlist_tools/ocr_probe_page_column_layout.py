from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from statistics import median
from typing import Iterable

from .ocr_column_row_segmentation import segment_page_rows
from .ocr_prepare_sequential_page import _load_source_image, read_jsonl, source_for_page
from .ocr_row_map_words import _persistent_left_rule_x

DEFAULT_STORE = Path("data/generated/ocr-page-column-layout.jsonl")


def parse_pages(spec: str) -> list[int]:
    pages: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            first_s, last_s = part.split("-", 1)
            first, last = int(first_s), int(last_s)
            step = 1 if last >= first else -1
            pages.extend(range(first, last + step, step))
        else:
            pages.append(int(part))
    return list(dict.fromkeys(pages))


def stable_mode(values: Iterable[int], *, radius: int = 1) -> int | None:
    """Return the centre of the densest small integer cluster."""
    values = list(values)
    if not values:
        return None
    counts = Counter(values)
    candidates = sorted(counts)
    best = max(
        candidates,
        key=lambda x: (
            sum(counts.get(x + delta, 0) for delta in range(-radius, radius + 1)),
            counts[x],
            -x,
        ),
    )
    cluster = [value for value in values if abs(value - best) <= radius]
    return int(round(median(cluster)))


def longest_low_run(counts: dict[int, int]) -> tuple[int, int, int] | None:
    """Return [left,right) for the longest near-empty vertical corridor.

    Scanner noise can make the clean gutter have one extra dark pixel in a
    column, so accept columns whose occupancy is at most minimum+1.
    """
    if not counts:
        return None
    minimum = min(counts.values())
    allowed = minimum + 1
    best: tuple[int, int] | None = None
    start: int | None = None
    previous: int | None = None
    for x in sorted(counts):
        if counts[x] <= allowed:
            if start is None or previous is None or x != previous + 1:
                start = x
        else:
            if start is not None and previous is not None:
                candidate = (start, previous + 1)
                if best is None or candidate[1] - candidate[0] > best[1] - best[0]:
                    best = candidate
            start = None
        previous = x
    if start is not None and previous is not None:
        candidate = (start, previous + 1)
        if best is None or candidate[1] - candidate[0] > best[1] - best[0]:
            best = candidate
    if best is None:
        return None
    return best[0], best[1], minimum


def _row_left_ink(page, row: dict, *, left: int, right: int, threshold: int) -> int | None:
    gray = page.convert("L")
    pixels = gray.load()
    top = max(0, int(row["page_top"]))
    bottom = min(gray.height, int(row["page_bottom"]))
    for x in range(max(0, left), min(gray.width, right)):
        if any(pixels[x, y] < threshold for y in range(top, bottom)):
            return x
    return None


def _column_start(page, entry: dict, *, threshold: int) -> tuple[int | None, list[int]]:
    left = int(entry["left"])
    right = int(entry["right"])
    rule_x = _persistent_left_rule_x(page, entry, threshold=threshold)
    search_left = max(left, rule_x + 2) if rule_x is not None else left
    search_right = min(right, search_left + max(20, (right - left) // 3))
    samples = [
        x
        for row in entry.get("rows") or []
        if (x := _row_left_ink(page, row, left=search_left, right=search_right, threshold=threshold)) is not None
    ]
    return stable_mode(samples), samples


def _vertical_ink_counts(page, *, left: int, right: int, top: int, bottom: int, threshold: int) -> dict[int, int]:
    gray = page.convert("L")
    pixels = gray.load()
    left = max(0, left)
    right = min(gray.width, right)
    top = max(0, top)
    bottom = min(gray.height, bottom)
    return {
        x: sum(1 for y in range(top, bottom) if pixels[x, y] < threshold)
        for x in range(left, right)
    }


def measure_page_layout(page, *, threshold: int = 210) -> dict:
    row_map = segment_page_rows(page, threshold=threshold)
    entries = list(row_map.get("columns") or [])
    starts: list[int | None] = []
    start_samples: list[list[int]] = []
    for entry in entries:
        start, samples = _column_start(page, entry, threshold=threshold)
        starts.append(start)
        start_samples.append(samples)

    body_rows = [row for entry in entries for row in entry.get("rows") or []]
    body_top = min((int(row["page_top"]) for row in body_rows), default=0)
    body_bottom = max((int(row["page_bottom"]) for row in body_rows), default=page.height)

    gutters: list[dict | None] = []
    boundaries: list[int | None] = []
    for index in range(len(entries) - 1):
        left_start = starts[index]
        right_start = starts[index + 1]
        if left_start is None or right_start is None or right_start <= left_start:
            gutters.append(None)
            boundaries.append(None)
            continue
        column_width = int(entries[index]["right"]) - int(entries[index]["left"])
        search_left = max(left_start + column_width // 2, int(entries[index]["left"]))
        search_right = right_start
        counts = _vertical_ink_counts(
            page,
            left=search_left,
            right=search_right,
            top=body_top,
            bottom=body_bottom,
            threshold=threshold,
        )
        run = longest_low_run(counts)
        if run is None:
            gutters.append(None)
            boundaries.append(None)
            continue
        gutter_left, gutter_right, minimum = run
        boundary = (gutter_left + gutter_right) // 2
        gutters.append(
            {
                "left": gutter_left,
                "right": gutter_right,
                "width": gutter_right - gutter_left,
                "minimum_vertical_ink": minimum,
            }
        )
        boundaries.append(boundary)

    return {
        "format": "saol-page-column-layout-v1",
        "page_size": [page.width, page.height],
        "threshold": threshold,
        "body_top": body_top,
        "body_bottom": body_bottom,
        "column_starts": starts,
        "column_start_sample_ranges": [
            [min(samples), max(samples)] if samples else None for samples in start_samples
        ],
        "gutters": gutters,
        "boundaries": boundaries,
    }


def _read_store(path: Path) -> dict[int, dict]:
    records: dict[int, dict] = {}
    if not path.exists():
        return records
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            records[int(record["page"])] = record
    return records


def _write_store(path: Path, records: dict[int, dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for page in sorted(records):
            handle.write(json.dumps(records[page], ensure_ascii=False, sort_keys=True) + "\n")


def _format_vector(values) -> str:
    return "[" + ", ".join("?" if value is None else str(value) for value in values) + "]"


def parity_summary(records: Iterable[dict]) -> list[str]:
    lines: list[str] = []
    records = list(records)
    for parity, name in ((0, "jämna"), (1, "udda")):
        group = [record for record in records if int(record["page"]) % 2 == parity]
        if not group:
            continue
        for key, width in (("column_starts", 3), ("boundaries", 2)):
            parts = []
            for index in range(width):
                values = [record[key][index] for record in group if record[key][index] is not None]
                if not values:
                    parts.append("?")
                else:
                    parts.append(f"{int(round(median(values)))} ({min(values)}..{max(values)})")
            lines.append(f"{name}: {key}=" + "[" + ", ".join(parts) + "]")
    return lines


def main() -> int:
    ap = argparse.ArgumentParser(description="Measure, remember and compare SAOL column geometry page by page.")
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--pages", required=True, help="Page list/range, e.g. 1-20 or 1,3,5")
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--store", type=Path, default=DEFAULT_STORE)
    args = ap.parse_args()

    pages = parse_pages(args.pages)
    all_rows = list(read_jsonl(args.jsonl))
    records = _read_store(args.store)
    for position, page_number in enumerate(pages, 1):
        print(f"page={page_number}: mäter kolumngeometri ({position}/{len(pages)}) ...", flush=True)
        source = source_for_page(all_rows, page_number)
        if not source:
            print(f"page={page_number}: ingen källbild", flush=True)
            continue
        page = _load_source_image(source)
        if page is None:
            print(f"page={page_number}: kunde inte läsa källbild", flush=True)
            continue
        measured = measure_page_layout(page, threshold=args.threshold)
        record = {"page": page_number, "parity": "even" if page_number % 2 == 0 else "odd", **measured}
        records[page_number] = record
        _write_store(args.store, records)
        print(
            f"page={page_number}: starts={_format_vector(record['column_starts'])} "
            f"boundaries={_format_vector(record['boundaries'])} "
            f"gutters={_format_vector([g['width'] if g else None for g in record['gutters'])}",
            flush=True,
        )

    print(f"sparat: {args.store}")
    for line in parity_summary(records.values()):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
