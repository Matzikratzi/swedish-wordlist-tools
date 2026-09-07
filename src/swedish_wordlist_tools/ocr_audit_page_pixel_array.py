from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from .ocr_glyph_matcher import load_facit
from .ocr_review_page_pixel_array_glyphs_html import (
    build_page_context_pixel_array,
    load_review_state_pixel_array,
)


class _TimestampedStdout:
    """Prefix every complete audit/review output line with elapsed wall time."""

    def __init__(self, stream, started: float):
        self.stream = stream
        self.started = started
        self.at_line_start = True

    def write(self, text: str) -> int:
        if not text:
            return 0
        for part in text.splitlines(keepends=True):
            if self.at_line_start:
                self.stream.write(f"[+{time.perf_counter() - self.started:8.3f}s] ")
                self.at_line_start = False
            self.stream.write(part)
            if part.endswith("\n") or part.endswith("\r"):
                self.at_line_start = True
        return len(text)

    def flush(self) -> None:
        self.stream.flush()

    def isatty(self) -> bool:
        return bool(getattr(self.stream, "isatty", lambda: False)())

    @property
    def encoding(self):
        return getattr(self.stream, "encoding", None)


def parse_pages(spec: str) -> list[int]:
    pages: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            first_text, last_text = part.split("-", 1)
            first = int(first_text)
            last = int(last_text)
            if last < first:
                raise ValueError(f"descending page range: {part}")
            pages.update(range(first, last + 1))
        else:
            pages.add(int(part))
    if not pages:
        raise ValueError("no pages selected")
    return sorted(pages)


def audit_page(jsonl: Path, page_number: int, models, *, threshold: int = 210) -> dict:
    print(f"audit: sida {page_number}: laddar och segmenterar ...", flush=True)
    page_started = time.perf_counter()
    context = build_page_context_pixel_array(jsonl, page_number, threshold)
    print(
        f"audit: sida {page_number}: sidförberedelse klar på "
        f"{time.perf_counter() - page_started:.3f} s",
        flush=True,
    )
    exact = 0
    defective: list[dict] = []
    by_column: dict[int, dict[str, int]] = {}

    # Deliberately sequential: increasing row number within each column.  This
    # mirrors the ownership model we are moving toward and avoids hiding order
    # dependencies behind the old parallel review cache.
    for column in range(len(context["row_map"].get("columns") or [])):
        positions = [position for position in context["positions"] if position[0] == column]
        positions.sort(key=lambda position: position[1])
        column_exact = 0
        column_defective = 0
        halfway = (len(positions) + 1) // 2
        column_started = time.perf_counter()
        print(
            f"audit: sida {page_number}: kolumn {column}: {len(positions)} rader",
            flush=True,
        )
        for local_index, position in enumerate(positions, start=1):
            row_started = time.perf_counter()
            state = load_review_state_pixel_array(context, position, models)
            row_seconds = time.perf_counter() - row_started
            if state["fully_exact"]:
                exact += 1
                column_exact += 1
            else:
                column_defective += 1
                defective.append(
                    {
                        "column": position[0],
                        "row": position[1],
                        "covered": state["covered_pixels"],
                        "source": state["source_pixels"],
                        "text": state["text"],
                    }
                )

            # Keep normal output compact but expose individual hot spots.
            if row_seconds >= 0.250:
                print(
                    f"audit: långsam rad c{position[0]} r{position[1]}: "
                    f"{row_seconds:.3f} s; "
                    f"{'exakt' if state['fully_exact'] else 'defekt'} "
                    f"{state['covered_pixels']}/{state['source_pixels']}",
                    flush=True,
                )

            if local_index == halfway and local_index < len(positions):
                print(
                    f"audit: sida {page_number}: kolumn {column} halvvägs "
                    f"({local_index}/{len(positions)}); exakt {column_exact}, "
                    f"defekta {column_defective}; "
                    f"{time.perf_counter() - column_started:.3f} s",
                    flush=True,
                )

        column_seconds = time.perf_counter() - column_started
        by_column[column] = {
            "exact": column_exact,
            "defective": column_defective,
            "milliseconds": round(column_seconds * 1000),
        }
        print(
            f"audit: sida {page_number}: kolumn {column} klar; "
            f"exakt {column_exact}/{len(positions)}, defekta {column_defective}; "
            f"{column_seconds:.3f} s",
            flush=True,
        )

    return {
        "page": page_number,
        "rows": len(context["positions"]),
        "exact": exact,
        "defective": defective,
        "by_column": by_column,
        "pixel_array_counts": context["pixel_owners"].counts(),
        "seconds": time.perf_counter() - page_started,
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Audit SAOL glyph coverage from the page-wide byte pixel array; no Tesseract."
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--pages", required=True, help="e.g. 1-10 or 1,3,8-10")
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--facit", type=Path, default=Path("glyphs/saol14-manual-glyph-facit.json"))
    args = ap.parse_args()

    run_started = time.perf_counter()
    original_stdout = sys.stdout
    sys.stdout = _TimestampedStdout(original_stdout, run_started)
    try:
        pages = parse_pages(args.pages)
        print(
            f"audit: startar {len(pages)} sidor: {', '.join(map(str, pages))}",
            flush=True,
        )
        print(f"audit: laddar facit {args.facit} ...", flush=True)
        models = load_facit(args.facit)
        print(f"audit: facit klart: {len(models)} glyphmodeller", flush=True)

        total_rows = 0
        total_exact = 0
        total_defective = 0
        for page_index, page_number in enumerate(pages, start=1):
            print(
                f"audit: ===== sida {page_number} ({page_index}/{len(pages)}) =====",
                flush=True,
            )
            result = audit_page(args.jsonl, page_number, models, threshold=args.threshold)
            total_rows += result["rows"]
            total_exact += result["exact"]
            total_defective += len(result["defective"])
            counts = result["pixel_array_counts"]
            print(
                f"page {page_number}: exact {result['exact']}/{result['rows']}; "
                f"defective {len(result['defective'])}; "
                f"unassigned ink {counts['unassigned_ink']}; "
                f"{result['seconds']:.3f} s",
                flush=True,
            )
            for defect in result["defective"]:
                print(
                    f"  c{defect['column']} r{defect['row']}: "
                    f"{defect['covered']}/{defect['source']} {defect['text']!r}",
                    flush=True,
                )

        print(
            f"TOTAL: exact {total_exact}/{total_rows}; defective {total_defective}; "
            f"{time.perf_counter() - run_started:.3f} s",
            flush=True,
        )
        return 0 if total_defective == 0 else 1
    finally:
        sys.stdout = original_stdout


if __name__ == "__main__":
    raise SystemExit(main())
