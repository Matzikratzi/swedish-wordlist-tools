from __future__ import annotations

"""Trace every owned-row OCR state in the order it is actually evaluated.

Diagnostic wrapper around the current isolated-context-anchor benchmark.  OCR
semantics are unchanged.  Every call to ``_load_owned_row_state`` is timed and
printed immediately, including the requested and returned (page, column, row),
row geometry, exactness, row baseline, and the actual selected glyph matches
with their individual baselines.

Repeated calls are intentionally retained: boundary repair and full fallback may
re-evaluate a position, and seeing those repetitions is part of the diagnostic.
The summary also reports timing distributions for individual calls and for each
unique row with all of its repeated-call time accumulated onto that row.
"""

from collections import Counter, defaultdict
from time import perf_counter

from . import ocr_isolated_context_anchor_benchmark as isolated
from . import ocr_review_page_pixel_array_glyphs_html as page_editor


_ORIGINAL = page_editor._load_owned_row_state
_COUNTS: Counter[tuple[int, int, int]] = Counter()
_CALL_TIMES: list[float] = []
_ROW_TIMES: dict[tuple[int, int, int], float] = defaultdict(float)
_ROW_TEXT: dict[tuple[int, int, int], str] = {}
_EVENT = 0

# Half-open millisecond buckets.  None means no upper bound.
_BUCKETS: tuple[tuple[str, float, float | None], ...] = (
    ("<10ms", 0.0, 0.010),
    ("10-20ms", 0.010, 0.020),
    ("20-50ms", 0.020, 0.050),
    ("50-100ms", 0.050, 0.100),
    ("100-500ms", 0.100, 0.500),
    (">=500ms", 0.500, None),
)


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
    page = int(context.get("page_number", -1))
    requested = (int(position[0]), int(position[1]))
    position_key = (page, requested[0], requested[1])
    _COUNTS[position_key] += 1
    occurrence = _COUNTS[position_key]
    _EVENT += 1
    event = _EVENT

    started = perf_counter()
    state = _ORIGINAL(context, position, models)
    elapsed = perf_counter() - started
    _CALL_TIMES.append(elapsed)
    _ROW_TIMES[position_key] += elapsed

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
    if text:
        _ROW_TEXT[position_key] = text

    print(
        "live-row: "
        f"event={event} call={occurrence} page={page} "
        f"requested=c{requested[0]}r{requested[1]} returned=c{returned[0]}r{returned[1]} "
        f"time={elapsed:.6f}s baseline={row_baseline!r} exact={exact} "
        f"coverage={covered}/{source} effective_y={effective_top}..{effective_bottom} "
        f"crop={crop_box!r} owner_rev={owner_revision} row_rev={row_revision} "
        f"text={text!r}",
        flush=True,
    )
    print(
        f"live-glyphs: event={event} page={page} c{returned[0]}r{returned[1]} count={len(matches)} "
        f"glyphs={glyphs!r}",
        flush=True,
    )
    return state


def _bucket_for(seconds: float) -> str:
    for label, lower, upper in _BUCKETS:
        if seconds >= lower and (upper is None or seconds < upper):
            return label
    raise AssertionError(seconds)


def _print_distribution(name: str, values: list[float]) -> None:
    total = sum(values)
    counts: Counter[str] = Counter()
    times: dict[str, float] = defaultdict(float)
    for value in values:
        label = _bucket_for(value)
        counts[label] += 1
        times[label] += value

    print(
        f"row-time-distribution-summary: scope={name} samples={len(values)} "
        f"total={total:.3f}s mean={(total / len(values) if values else 0.0):.6f}s",
        flush=True,
    )
    for label, _lower, _upper in _BUCKETS:
        count = counts[label]
        elapsed = times[label]
        pct_samples = 100.0 * count / len(values) if values else 0.0
        pct_time = 100.0 * elapsed / total if total else 0.0
        print(
            "row-time-bucket: "
            f"scope={name} bucket={label} count={count} sample_pct={pct_samples:.1f} "
            f"time={elapsed:.3f}s time_pct={pct_time:.1f}",
            flush=True,
        )


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
            f"live-row-repeat: rank={rank} page={position[0]} column={position[1]} "
            f"row={position[2]} calls={count}",
            flush=True,
        )

    _print_distribution("calls", list(_CALL_TIMES))
    _print_distribution("unique-rows-accumulated", list(_ROW_TIMES.values()))

    print("slowest-accumulated-rows: top=4", flush=True)
    for rank, (position, elapsed) in enumerate(
        sorted(_ROW_TIMES.items(), key=lambda item: (-item[1], item[0]))[:4],
        start=1,
    ):
        text = _ROW_TEXT.get(position, "")
        print(
            "slowest-accumulated-row: "
            f"rank={rank} page={position[0]} column={position[1]} row={position[2]} "
            f"calls={_COUNTS[position]} time={elapsed:.3f}s text={text!r}",
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
