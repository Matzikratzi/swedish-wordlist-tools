from __future__ import annotations

"""Benchmark an explicit first-glyph typography priority without changing OCR semantics.

This experiment only changes candidate ordering. The candidate set, exact raster
matching, baseline rules, recursion and fallback paths are unchanged.

Priority at the first glyph:
- headword row: bold -> roman -> italic -> unknown
- continuation/unknown row: roman -> italic -> bold -> unknown
- homonym row: homonym digit -> bold -> roman -> italic -> unknown

Subsequent-glyph ordering keeps the existing same-style stickiness and homonym
baseline behaviour from ocr_priority_fast_path.
"""

from . import ocr_priority_fast_path as priority
from .ocr_split_facit_benchmark import main as benchmark_main


def _explicit_style_priority_class(
    model,
    *,
    first_glyph: bool,
    previous_style: str | None,
    row_kind: str,
    leading_homonym_seen: bool,
    baseline_established: bool,
) -> int:
    typography = priority._typographic_style(model.style)

    if first_glyph:
        if row_kind == "homonym":
            if priority._is_homonym_model(model):
                return 0
            return {
                "bold": 1,
                "roman": 2,
                "italic": 3,
                "unknown": 4,
            }.get(typography, 4)

        if row_kind == "headword":
            return {
                "bold": 0,
                "roman": 1,
                "italic": 2,
                "unknown": 3,
            }.get(typography, 3)

        # Continuation and not-yet-classified rows are overwhelmingly body text.
        return {
            "roman": 0,
            "italic": 1,
            "bold": 2,
            "unknown": 3,
        }.get(typography, 3)

    # Preserve the existing post-first-glyph semantics exactly.
    if row_kind == "homonym" and leading_homonym_seen and not baseline_established:
        return 0 if priority._is_headword_model(model) else 1

    if previous_style is not None:
        if typography == previous_style:
            return 0
        if row_kind == "continuation" and priority._is_headword_model(model):
            return 2

    return 1


def main() -> int:
    original = priority._priority_class
    priority._priority_class = _explicit_style_priority_class
    try:
        print(
            "style-priority: first=headword:bold>roman>italic "
            "continuation/unknown:roman>italic>bold "
            "homonym:digit>bold>roman>italic",
            flush=True,
        )
        return benchmark_main()
    finally:
        priority._priority_class = original


if __name__ == "__main__":
    raise SystemExit(main())
