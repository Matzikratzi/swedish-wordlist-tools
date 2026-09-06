from __future__ import annotations

"""Benchmark the existing split facit store without changing OCR semantics.

The split store is loaded in stable model-id order (g000001, g000002, ...),
then compared model-for-model with the monolithic v2 facit before any page is
scanned.  The OCR scanner itself is unchanged.
"""

import argparse
import json
import time
from pathlib import Path

from . import ocr_review_page_pixel_array_glyphs_html as page_editor
from .ocr_compare_forward_reference import (
    _actual_rows,
    _compare_page,
    _load_reference,
    _short_text,
    _timed_rows,
)
from .ocr_find_unreviewed_glyph_rows import _available_pages, _selected_pages
from .ocr_forward_page_scan import scan_page_forward
from .ocr_glyph_review_delete import (
    TYPOGRAPHIC_STYLES,
    _RoleWithTypography,
    load_facit_with_typography,
)
from . import ocr_glyph_matcher as matcher


def _model_id_key(path: Path) -> int:
    stem = path.stem
    if stem.startswith("g") and stem[1:].isdigit():
        return int(stem[1:])
    raise ValueError(f"unexpected split facit filename: {path}")


def load_split_facit_with_typography(directory: Path) -> list[matcher.GlyphModel]:
    meta_path = directory / "_meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if meta.get("format") != "saol14-manual-glyph-facit-v2":
        raise ValueError(f"unsupported split facit format in {meta_path}")

    files = sorted(directory.rglob("g*.json"), key=_model_id_key)
    out: list[matcher.GlyphModel] = []
    seen_ids: set[int] = set()

    for path in files:
        model_id = _model_id_key(path)
        if model_id in seen_ids:
            raise ValueError(f"duplicate split facit model id g{model_id:06d}")
        seen_ids.add(model_id)

        row = json.loads(path.read_text(encoding="utf-8"))
        payload_id = str(row.get("model_id") or "")
        expected_id = f"g{model_id:06d}"
        if payload_id and payload_id != expected_id:
            raise ValueError(
                f"split facit id mismatch: {path} says {payload_id!r}, expected {expected_id!r}"
            )

        points = frozenset(
            (int(x), int(y))
            for x, y in row.get("pixels_relative_to_baseline") or []
        )
        if not points:
            continue

        role = str(row.get("role") or "unknown")
        typographic_style = str(row.get("style") or "roman")
        if typographic_style not in TYPOGRAPHIC_STYLES:
            typographic_style = "roman"

        out.append(
            matcher.GlyphModel(
                label=str(row.get("label") or ""),
                style=_RoleWithTypography(
                    role,
                    typographic_style,
                    bool(row.get("reviewed", False)),
                ),
                pixels=points,
                sources=len(row.get("sources") or []),
            )
        )

    return out


def _model_signature(model: matcher.GlyphModel) -> tuple:
    return (
        model.label,
        str(model.style),
        getattr(model.style, "typographic_style", None),
        bool(getattr(model.style, "reviewed", False)),
        tuple(sorted(model.pixels)),
        int(model.sources),
    )


def _verify_equivalent(monolithic, split) -> None:
    if len(monolithic) != len(split):
        raise ValueError(
            f"facit model count differs: monolithic={len(monolithic)} split={len(split)}"
        )
    for index, (left, right) in enumerate(zip(monolithic, split)):
        lsig = _model_signature(left)
        rsig = _model_signature(right)
        if lsig != rsig:
            raise ValueError(
                f"facit model differs at index={index}: "
                f"monolithic={lsig[:4]!r} split={rsig[:4]!r}"
            )


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Benchmark split SAOL glyph facit against the monolithic baseline."
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--facit", type=Path, required=True, help="monolithic v2 facit")
    ap.add_argument("--split-facit", type=Path, required=True, help="split facit-v2 directory")
    ap.add_argument("--reference-dir", type=Path, required=True)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--page", type=int, action="append", dest="pages")
    ap.add_argument("--start-page", type=int)
    ap.add_argument("--end-page", type=int)
    ap.add_argument("--boundary-radius", type=int, default=6)
    ap.add_argument("--max-diffs", type=int, default=20)
    args = ap.parse_args()

    t0 = time.perf_counter()
    monolithic = load_facit_with_typography(args.facit)
    mono_load = time.perf_counter() - t0

    t0 = time.perf_counter()
    models = load_split_facit_with_typography(args.split_facit)
    split_load = time.perf_counter() - t0

    _verify_equivalent(monolithic, models)
    print(
        f"facit-equivalent: models={len(models)} order=identical "
        f"monolithic_load={mono_load:.6f}s split_load={split_load:.6f}s",
        flush=True,
    )

    pages = _selected_pages(
        _available_pages(args.jsonl),
        pages=args.pages,
        start_page=args.start_page,
        end_page=args.end_page,
    )
    if not pages:
        raise ValueError("no pages selected")

    total_reference = 0
    total_actual = 0
    total_equal = 0
    total_mismatches = 0
    total_final_exact = 0
    total_rows = 0
    total_fallback = 0
    printed_diffs = 0
    timings = []
    scan_start = time.perf_counter()

    for page in pages:
        reference = _load_reference(args.reference_dir / f"page-{page:03d}.jsonl")
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
        exact = sum(1 for row in actual.values() if row["exact"])

        total_reference += len(reference)
        total_actual += len(actual)
        total_equal += equal
        total_mismatches += len(mismatches)
        total_final_exact += exact
        total_rows += len(actual)
        total_fallback += len(fallback_rows)

        print(
            f"split-facit: page={page} rows={len(actual)} final_exact={exact}/{len(actual)} "
            f"reference_equal={equal}/{len(all_keys)} mismatches={len(mismatches)} "
            f"fallback={len(fallback_rows)}",
            flush=True,
        )

        for key, why, expected, observed in mismatches:
            if printed_diffs >= args.max_diffs:
                break
            printed_diffs += 1
            print(f"DIFF page={page} column={key[0]} row={key[1]}: {why}", flush=True)
            if expected is not None:
                print(
                    f"  ref pixels={expected['source_pixels']} text={expected['text']!r}",
                    flush=True,
                )
            if observed is not None:
                print(
                    f"  new pixels={observed['source_pixels']} covered={observed['covered_pixels']} "
                    f"exact={observed['exact']} text={observed['text']!r}",
                    flush=True,
                )

    scan_wall = time.perf_counter() - scan_start
    print(
        "split-facit-summary: "
        f"pages={len(pages)} rows={total_rows} final_exact={total_final_exact}/{total_rows} "
        f"reference_rows={total_reference} actual_rows={total_actual} "
        f"reference_equal={total_equal} mismatches={total_mismatches} "
        f"fallback={total_fallback} scan_wall={scan_wall:.3f}s "
        f"monolithic_load={mono_load:.6f}s split_load={split_load:.6f}s",
        flush=True,
    )

    print("slowest-rows: top=4", flush=True)
    for rank, item in enumerate(
        sorted(timings, key=lambda row: row.elapsed, reverse=True)[:4], start=1
    ):
        kind = "fallback" if item.fallback else "fast"
        print(
            f"slowest-row: rank={rank} page={item.page} column={item.column} row={item.row} "
            f"time={item.elapsed:.3f}s path={kind} text={_short_text(item.text)!r}",
            flush=True,
        )

    return 1 if total_mismatches else 0


if __name__ == "__main__":
    raise SystemExit(main())
