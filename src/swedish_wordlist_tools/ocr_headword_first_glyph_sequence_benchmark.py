from __future__ import annotations

"""Benchmark previous-headword glyph reuse at the actual page-scan level.

The scanner keeps the exact glyph-model sequence of the most recently proven
headword across intervening continuation rows.  Before each physical row is
analysed we classify its start from page ownership / learned headword x.  Only
headword and homonym rows receive the previous sequence as an OCR ordering hint.

After every exact row, proven match geometry is fed back to the existing layout
observer.  This lets an early exact bold headword teach the physical headword x
without relying on thread-local state after nested fallback wrappers.

For a headword row the ordinary exact-cover search therefore tries the previous
headword's exact first glyph raster first.  A successful first glyph establishes
baseline immediately.  At later positions the previous exact glyph sequence is
tried first; full/half boundary marks may be inserted without consuming the
sequence index.  The original candidate set remains available, so acceptance
semantics are unchanged.
"""

from collections import Counter
from time import perf_counter

from . import ocr_context_anchor_benchmark as context_anchor
from . import ocr_fast_regression_scan as fast_regression
from . import ocr_forward_page_scan as forward
from . import ocr_page_cached_fast_path as cached
from . import ocr_previous_headword_glyph_sequence_benchmark as sequence
from . import ocr_priority_fast_path as priority
from . import ocr_review_page_pixel_array_glyphs_html as page_editor
from . import ocr_single_downshift_safe_islands_benchmark as downstream


_STATS: Counter[str] = Counter()
_PREVIOUS_SEQUENCE: tuple | None = None
_LAST_PAGE: int | None = None


def _match_model_signature(match):
    """Recover the exact normalized facit raster from a placed Match."""
    x0 = int(getattr(match, "x", 0))
    baseline = int(getattr(match, "baseline", 0))
    pixels = tuple(
        sorted(
            (int(x) - x0, int(y) - baseline)
            for x, y in getattr(match, "pixels", ())
        )
    )
    return (str(getattr(match, "label", "")), str(getattr(match, "style", "")), pixels)


def _headword_sequence_from_exact_state(state: dict) -> tuple | None:
    matches = list(state.get("matches") or state.get("selected") or [])
    matches.sort(key=lambda m: (int(getattr(m, "x", 0)), int(getattr(m, "baseline", 0))))
    if not matches:
        return None

    index = 0
    if priority._is_homonym_match(matches[0]):
        index = 1
    if index >= len(matches) or not priority._is_headword_match(matches[index]):
        return None

    out = []
    started = False
    for match in matches[index:]:
        label = str(getattr(match, "label", ""))
        if priority._is_headword_match(match):
            started = True
            out.append(_match_model_signature(match))
            continue
        if started and label in sequence._BREAKS:
            out.append(_match_model_signature(match))
            continue
        if started:
            break
    return tuple(out) if out else None


def _set_sequence_hint(kind: str) -> None:
    if kind in {"headword", "homonym"} and _PREVIOUS_SEQUENCE:
        priority._tls.previous_headword_glyph_sequence = _PREVIOUS_SEQUENCE
        _STATS["headword_calls_with_previous"] += 1
    else:
        priority._tls.previous_headword_glyph_sequence = None


def _observe_exact(context: dict, state: dict, kind_before: str) -> None:
    global _PREVIOUS_SEQUENCE
    if not state.get("fully_exact"):
        return

    # Existing observer learns stable absolute headword/homonym x from exact
    # facit evidence.  This is intentionally after exact proof only.
    priority.observe_row_layout(context, state)

    found = _headword_sequence_from_exact_state(state)
    if found:
        _PREVIOUS_SEQUENCE = found
        _STATS["observed_headwords"] += 1
        _STATS["stored_glyphs"] += len(found)
        if kind_before == "unknown":
            _STATS["headwords_that_taught_layout"] += 1


def _scan_page_fast_with_headword_memory(
    context: dict,
    models,
    *,
    boundary_radius: int = 6,
):
    global _PREVIOUS_SEQUENCE, _LAST_PAGE

    page = int(context["page_number"])
    if _LAST_PAGE is None:
        _LAST_PAGE = page
    elif page != _LAST_PAGE:
        # SAOL order continues across pages, so deliberately keep the previous
        # headword sequence.  Only the learned x counters themselves are page-local.
        _LAST_PAGE = page

    cached.bind_page_candidates(context, models)
    rows = []

    with fast_regression._fast_only_analyser():
        for position in context["positions"]:
            kind = priority.classify_row_start(context, position)
            _STATS[f"classified_{kind}"] += 1
            priority.set_row_priority_hint(kind)
            _set_sequence_hint(kind)

            started = perf_counter()
            state = page_editor._load_owned_row_state(context, position, models)
            initial_elapsed = perf_counter() - started
            _observe_exact(context, state, kind)

            repair = None
            if not state.get("fully_exact") and boundary_radius >= 0:
                repair = fast_regression.try_fast_boundary_repair(
                    context, position, models, radius=boundary_radius
                )
                if repair.repaired:
                    kind = priority.classify_row_start(context, position)
                    priority.set_row_priority_hint(kind)
                    _set_sequence_hint(kind)
                    state = page_editor._load_owned_row_state(context, position, models)
                    _observe_exact(context, state, kind)

            repair_elapsed = repair.elapsed if repair is not None else 0.0
            rows.append(
                fast_regression.FastRegressionRow(
                    page=page,
                    column=int(position[0]),
                    row=int(position[1]),
                    exact=bool(state.get("fully_exact")),
                    source_pixels=int(state.get("source_pixels") or 0),
                    covered_pixels=int(state.get("covered_pixels") or 0),
                    elapsed=initial_elapsed + repair_elapsed,
                    text=str(state.get("text") or ""),
                    repaired=bool(repair and repair.repaired),
                    moved_pixels=int(repair.moved_pixels if repair else 0),
                    repair_attempts=int(repair.attempts if repair else 0),
                    repair_elapsed=repair_elapsed,
                    cut_y=repair.cut_y if repair else None,
                    repair_strategy=repair.strategy if repair else None,
                )
            )

    return rows


def _print_stats() -> None:
    seq_stats = sequence._STATS
    print(
        "headword-sequence-scan-summary: "
        f"classified_headword={_STATS['classified_headword']} "
        f"classified_homonym={_STATS['classified_homonym']} "
        f"classified_continuation={_STATS['classified_continuation']} "
        f"classified_unknown={_STATS['classified_unknown']} "
        f"headword_calls_with_previous={_STATS['headword_calls_with_previous']} "
        f"observed_headwords={_STATS['observed_headwords']} "
        f"headwords_that_taught_layout={_STATS['headwords_that_taught_layout']} "
        f"stored_glyphs={_STATS['stored_glyphs']} "
        f"sequence_calls_with_previous={seq_stats['calls_with_previous']} "
        f"sequence_states={seq_stats['sequence_states']} "
        f"expected_promotions={seq_stats['expected_promotions']} "
        f"expected_fits={seq_stats['expected_fits']} "
        f"break_fits={seq_stats['break_fits']} "
        f"sequence_diverged={seq_stats['sequence_diverged']} "
        f"states={seq_stats['states']} placements={seq_stats['placements']}",
        flush=True,
    )


def main() -> int:
    original_forward_scan = forward.scan_page_fast
    original_context_ordinary = context_anchor._ORIGINAL
    original_context_fixed = context_anchor._fixed_baseline_exact_cover

    forward.scan_page_fast = _scan_page_fast_with_headword_memory
    context_anchor._ORIGINAL = sequence._sequence_exact_cover
    # Keep the existing fixed-baseline anchor path unchanged.  The major test
    # here is whether the known first headword glyph cheaply establishes baseline
    # on ordinary headword rows.
    context_anchor._fixed_baseline_exact_cover = sequence._sequence_fixed_baseline_exact_cover

    try:
        result = downstream.main()
    finally:
        forward.scan_page_fast = original_forward_scan
        context_anchor._ORIGINAL = original_context_ordinary
        context_anchor._fixed_baseline_exact_cover = original_context_fixed
        if hasattr(priority._tls, "previous_headword_glyph_sequence"):
            del priority._tls.previous_headword_glyph_sequence

    _print_stats()
    return result


if __name__ == "__main__":
    raise SystemExit(main())
