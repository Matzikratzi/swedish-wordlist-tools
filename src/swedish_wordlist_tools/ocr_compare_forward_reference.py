from __future__ import annotations

"""Compare the historical fast-forward OCR scanner with frozen page references.

Diagnostic only: OCR behaviour is unchanged.  Each page is scanned with
``ocr_forward_page_scan.scan_page_forward`` and the final row result (fast path
or fallback) is compared with the frozen JSONL reference.

The comparison mirrors the proven ad-hoc page-1 validation used when selecting
commit 2728f11 as a historical performance baseline:

* same (column, row) keys;
* every actual row must be exact;
* same row text;
* same source pixel count.

A final TOP 4 report shows the slowest rows across the run.  For rows that fall
back, elapsed time is fast-path time plus fallback time.
"""

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from . import ocr_review_page_pixel_array_glyphs_html as page_editor
from .ocr_find_unreviewed_glyph_rows import _available_pages, _selected_pages
from .ocr_forward_page_scan import scan_page_forward
from .ocr_glyph_review_delete import load_facit_with_typography


@dataclass(frozen=True)
class TimedRow:
    page: int
    column: int
    row: int
    elapsed: float
    text: str
    fallback: bool


def _load_reference(path: Path) -> dict[tuple[int, int], dict]:
    rows: dict[tuple[int, int], dict] = {}
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            item = json.loads(line)
            rows[(int(item["column"]), int(item["row"]))] = item
    return rows


def _actual_rows(fast_rows, fallback_rows) -> dict[tuple[int, int], dict]:
    fallback = {(row.column, row.row): row for row in fallback_rows}
    actual: dict[tuple[int, int], dict] = {}
    for row in fast_rows:
        key = (row.column, row.row)
        final = fallback.get(key, row)
        actual[key] = {
            "exact": bool(final.exact),
            "text": str(final.text),
            "source_pixels": int(final.source_pixels),
            "covered_pixels": int(final.covered_pixels),
        }
    return actual


def _timed_rows(page: int, fast_rows, fallback_rows) -> list[TimedRow]:
    fallback = {(row.column, row.row): row for row in fallback_rows}
    result: list[TimedRow] = []
    for row in fast_rows:
        key = (row.column, row.row)
        slow = fallback.get(key)
        result.append(
            TimedRow(
                page=page,
                column=row.column,
                row=row.row,
                elapsed=float(row.elapsed) + (float(slow.elapsed) if slow else 0.0),
                text=str((slow.text if slow else row.text) or ""),
                fallback=slow is not None,
            )
        )
    return result


def _compare_page(reference: dict, actual: dict) -> list[tuple]:
    mismatches: list[tuple] = []
    all_keys = sorted(set(reference) | set(actual))

    for key in all_keys:
        expected = reference.get(key)
        observed = actual.get(key)

        if expected is None:
            mismatches.append((key, "EXTRA", None, observed))
            continue
        if observed is None:
            mismatches.append((key, "MISSING", expected, None))
            continue

        problems: list[str] = []
        if not observed["exact"]:
            problems.append("not-exact")
        if observed["text"] != expected["text"]:
            problems.append("text")
        if observed["source_pixels"] != int(expected["source_pixels"]):
            problems.append(
                f"source_pixels {observed['source_pixels']} != {expected['source_pixels']}"
            )

        if problems:
            mismatches.append((key, ", ".join(problems), expected, observed))

    return mismatches


def _short_text(text: str, width: int = 110) -> str:
    text = " ".join(text.split())
    if len(text) <= width:
        return text
    return text[: max(0, width - 1)] + "…"


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Compare historical fast-forward OCR rows with frozen references."
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--facit", type=Path, required=True)
    ap.add_argument("--reference-dir", type=Path, required=True)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--page", type=int, action="append", dest="pages")
    ap.add_argument("--start-page", type=int)
    ap.add_argument("--end-page", type=int)
    ap.add_argument("--boundary-radius", type=int, default=6)
    ap.add_argument("--max-diffs", type=int, default=20)
    args = ap.parse_args()

    pages = _selected_pages(
        _available_pages(args.jsonl),
        pages=args.pages,
        start_page=args.start_page,
        end_page=args.end_page,
    )
    if not pages:
        raise ValueError("no pages selected")

    models = load_facit_with_typography(args.facit)
    total_reference = 0
    total_actual = 0
    total_equal = 0
    total_mismatches = 0
    printed_diffs = 0
    timings: list[TimedRow] = []

    for page in pages:
        reference_path = args.reference_dir / f"page-{page:03d}.jsonl"
        reference = _load_reference(reference_path)

        context = page_editor.build_page_context_pixel_array(
            args.jsonl, page, args.threshold
        )
        context["quiet_successful_ownership"] = True
        fast_rows, fallback_rows = scan_page_forward(
            context, models, boundary_radius=args.boundary_radius
        )
        actual = _actual_rows(fast_rows, fallback_rows)
        timings.extend(_timed_rows(page, fast_rows, fallback_rows))
        mismatches = _compare_page(reference, actual)

        all_keys = set(reference) | set(actual)
        equal = len(all_keys) - len(mismatches)
        total_reference += len(reference)
        total_actual += len(actual)
        total_equal += equal
        total_mismatches += len(mismatches)

        print(
            f"reference-compare: page={page} reference_rows={len(reference)} "
            f"actual_rows={len(actual)} equal={equal}/{len(all_keys)} "
            f"mismatches={len(mismatches)} fallback={len(fallback_rows)}",
            flush=True,
        )

        for key, why, expected, observed in mismatches:
            if printed_diffs >= args.max_diffs:
                break
            printed_diffs += 1
            print(
                f"DIFF page={page} column={key[0]} row={key[1]}: {why}",
                flush=True,
            )
            if expected is not None:
                print(
                    f"  ref pixels={expected['source_pixels']} "
                    f"text={expected['text']!r}",
                    flush=True,
                )
            if observed is not None:
                print(
                    f"  new pixels={observed['source_pixels']} "
                    f"covered={observed['covered_pixels']} exact={observed['exact']} "
                    f"text={observed['text']!r}",
                    flush=True,
                )

    print(
        "reference-compare-summary: "
        f"pages={len(pages)} reference_rows={total_reference} "
        f"actual_rows={total_actual} equal={total_equal} "
        f"mismatches={total_mismatches}",
        flush=True,
    )

    print("slowest-rows: top=4", flush=True)
    for rank, item in enumerate(
        sorted(timings, key=lambda row: row.elapsed, reverse=True)[:4], start=1
    ):
        kind = "fallback" if item.fallback else "fast"
        print(
            f"slowest-row: rank={rank} page={item.page} column={item.column} "
            f"row={item.row} time={item.elapsed:.3f}s path={kind} "
            f"text={_short_text(item.text)!r}",
            flush=True,
        )

    return 1 if total_mismatches else 0


if __name__ == "__main__":
    raise SystemExit(main())
