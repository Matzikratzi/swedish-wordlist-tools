from __future__ import annotations

"""Trace every owned-row OCR state in the order it is actually evaluated.

Diagnostic wrapper around the current isolated-context-anchor benchmark.  OCR
semantics are unchanged.  Every call to ``_load_owned_row_state`` is timed and
printed immediately, including the requested and returned (column, row), row
geometry, exactness, row baseline, and the actual selected glyph matches with
their individual baselines.

Repeated calls are intentionally retained: boundary repair and full fallback may
re-evaluate a position, and seeing those repetitions is part of the diagnostic.
"""

from collections import Counter
from time import perf_counter

from . import ocr_isolated_context_anchor_benchmark as isolated
from . import ocr_review_page_pixel_array_glyphs_html as page_editor


_ORIGINAL = page_editor._load_owned_row_state
_COUNTS: Counter[tuple[int, int]] = Counter()
_EVENT = 0


def _match_token(match) -> str:
    label = str(getattr(match, "label", "?"))
    baseline = getattr(match, "baseline", None)
    x = getattr(match, "x", None)
    if baseline is None:
        return f"{label}@?"
    if x is None:
        return f"{label}@{baseline}"
    return f"{label}@{baseline}:x{x}"


def _traced_load_owned_row_state(context: dict, position: tuple[int, int], models) -> dict:
    global _EVENT
    requested = (int(position[0]), int(position[1]))
    _COUNTS[requested] += 1
    occurrence = _COUNTS[requested]
    _EVENT += 1
    event = _EVENT

    started = perf_counter()
    state = _ORIGINAL(context, position, models)
    elapsed = perf_counter() - started

    returned = (int(state.get("column", -1)), int(state.get("row", -1)))
    matches = list(state.get("matches") or [])
    glyphs = " ".join(_match_token(match) for match in matches)
    row_baseline = state.get("baseline")
    exact = bool(state.get("fully_exact"))
    covered = int(state.get("covered_pixels") or 0)
    source = int(state.get("source_pixels") or 0)
    crop_box = state.get("crop_box")
    effective_top = state.get("effective_row_page_top")
    effective_bottom = state.get("effective_row_page_bottom")
    owner_revision = state.get("pixel_owner_revision")
    row_revision = state.get("pixel_owner_row_revision")
    text = str(state.get("text") or "")

    print(
        "live-row: "
        f"event={event} call={occurrence} page={int(context.get('page_number', -1))} "
        f"requested=c{requested[0]}r{requested[1]} returned=c{returned[0]}r{returned[1]} "
        f"time={elapsed:.6f}s baseline={row_baseline!r} exact={exact} "
        f"coverage={covered}/{source} effective_y={effective_top}..{effective_bottom} "
        f"crop={crop_box!r} owner_rev={owner_revision} row_rev={row_revision} "
        f"text={text!r}",
        flush=True,
    )
    print(
        f"live-glyphs: event={event} c{returned[0]}r{returned[1]} count={len(matches)} "
        f"glyphs={glyphs!r}",
        flush=True,
    )
    return state


def _print_summary() -> None:
    repeated = sorted(
        ((position, count) for position, count in _COUNTS.items() if count > 1),
        key=lambda item: (-item[1], item[0]),
    )
    print(
        f"live-row-summary: events={_EVENT} unique_positions={len(_COUNTS)} "
        f"repeated_positions={len(repeated)}",
        flush=True,
    )
    for rank, (position, count) in enumerate(repeated[:20], start=1):
        print(
            f"live-row-repeat: rank={rank} column={position[0]} row={position[1]} calls={count}",
            flush=True,
        )


def main() -> int:
    page_editor._load_owned_row_state = _traced_load_owned_row_state
    try:
        result = isolated.main()
    finally:
        page_editor._load_owned_row_state = _ORIGINAL
    _print_summary()
    return result


if __name__ == "__main__":
    raise SystemExit(main())
