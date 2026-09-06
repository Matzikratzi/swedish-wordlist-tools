from __future__ import annotations

"""Repair stale OCR reference pixel accounting without blessing OCR text changes.

This command is deliberately narrow.  It only updates an existing frozen
reference row when the current shared OCR parser:

* produces exactly the same text as the reference;
* fully covers the current source row exactly; and
* has different source/covered pixel counts than the frozen reference.

Rows with text differences, non-exact OCR, missing rows, extra rows, or only an
old ``exact`` flag are left untouched.  This is intended for repairing frozen
references created while older crop/compaction logic could discard already
matched edge pixels.
"""

import argparse
import json
from pathlib import Path

from . import ocr_review_page_pixel_array_glyphs_html as page_editor
from .ocr_compare_forward_reference import _actual_rows, _load_reference
from .ocr_find_unreviewed_glyph_rows import _available_pages, _selected_pages
from .ocr_forward_page_scan import scan_page_forward
from .ocr_glyph_review_delete import load_facit_with_typography


def _write_reference(path: Path, rows: dict[tuple[int, int], dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for key in sorted(rows):
            fh.write(json.dumps(rows[key], ensure_ascii=False, sort_keys=True) + "\n")


def _repair_page(reference: dict, actual: dict) -> tuple[dict, list[tuple], list[tuple]]:
    repaired = {key: dict(value) for key, value in reference.items()}
    changed: list[tuple] = []
    unresolved: list[tuple] = []

    for key in sorted(set(reference) | set(actual)):
        expected = reference.get(key)
        observed = actual.get(key)

        if expected is None:
            unresolved.append((key, "EXTRA", expected, observed))
            continue
        if observed is None:
            unresolved.append((key, "MISSING", expected, observed))
            continue
        if str(expected.get("text") or "") != str(observed.get("text") or ""):
            unresolved.append((key, "text", expected, observed))
            continue
        if not bool(observed.get("exact", False)):
            unresolved.append((key, "not-exact", expected, observed))
            continue

        source_pixels = int(observed.get("source_pixels") or 0)
        covered_pixels = int(observed.get("covered_pixels") or 0)
        if source_pixels <= 0 or covered_pixels != source_pixels:
            unresolved.append((key, "not-fully-covered", expected, observed))
            continue

        expected_source = int(expected.get("source_pixels") or 0)
        expected_covered = int(expected.get("covered_pixels") or 0)

        # This command repairs pixel accounting only.  An old exact=False flag
        # with identical pixel counts is intentionally not a REPAIR.
        if expected_source == source_pixels and expected_covered == covered_pixels:
            continue

        row = repaired[key]
        row["source_pixels"] = source_pixels
        row["covered_pixels"] = covered_pixels
        row["exact"] = True
        changed.append(
            (
                key,
                expected_source,
                source_pixels,
                expected_covered,
                covered_pixels,
                str(observed.get("text") or ""),
            )
        )

    return repaired, changed, unresolved


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Repair only stale exact pixel accounting in frozen SAOL OCR references."
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--facit", type=Path, required=True)
    ap.add_argument("--reference-dir", type=Path, required=True)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--page", type=int, action="append", dest="pages")
    ap.add_argument("--start-page", type=int)
    ap.add_argument("--end-page", type=int)
    ap.add_argument("--boundary-radius", type=int, default=6)
    ap.add_argument(
        "--write",
        action="store_true",
        help="write repaired references; without this flag the command is dry-run only",
    )
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
    total_changed = 0
    total_unresolved = 0

    for page in pages:
        reference_path = args.reference_dir / f"page-{page:03d}.jsonl"
        reference = _load_reference(reference_path)
        context = page_editor.build_page_context_pixel_array(args.jsonl, page, args.threshold)
        context["quiet_successful_ownership"] = True
        fast_rows, fallback_rows = scan_page_forward(
            context, models, boundary_radius=args.boundary_radius
        )
        actual = _actual_rows(fast_rows, fallback_rows)
        repaired, changed, unresolved = _repair_page(reference, actual)

        for key, old_source, new_source, old_covered, new_covered, text in changed:
            print(
                f"REPAIR page={page} column={key[0]} row={key[1]} "
                f"source_pixels {old_source} -> {new_source}; "
                f"covered_pixels {old_covered} -> {new_covered}; text={text!r}",
                flush=True,
            )
        for key, why, expected, observed in unresolved:
            print(
                f"UNRESOLVED page={page} column={key[0]} row={key[1]}: {why}",
                flush=True,
            )

        if args.write and changed:
            _write_reference(reference_path, repaired)

        total_changed += len(changed)
        total_unresolved += len(unresolved)
        print(
            f"reference-repair: page={page} repairable={len(changed)} "
            f"unresolved={len(unresolved)} mode={'write' if args.write else 'dry-run'}",
            flush=True,
        )

    print(
        f"reference-repair-summary: pages={len(pages)} repaired={total_changed if args.write else 0} "
        f"repairable={total_changed} unresolved={total_unresolved} "
        f"mode={'write' if args.write else 'dry-run'}",
        flush=True,
    )
    return 1 if total_unresolved else 0


if __name__ == "__main__":
    raise SystemExit(main())
