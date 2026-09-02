from __future__ import annotations

import json
import threading

from . import ocr_review_five_rows_glyphs_ultrafast_html as ultrafast
from .ocr_blank_row_boundary import find_blank_row_boundary
from .ocr_row_boundary_corrections import (
    BoundaryCorrectionStore,
    apply_boundary_corrections,
    evaluate_boundary,
    find_boundary_correction,
    model_digest,
    page_digest,
)


fast = ultrafast.fast
_original_load_review_state = fast.load_review_state_fast
_original_diagnostic_text = ultrafast.diagnostic_text
_original_state_cache = fast.SynchronizedStateCache
_original_row_crop_box = fast._row_crop_box
_context_lock = threading.RLock()
_boundary_generation_lock = threading.RLock()
_boundary_generation = 0


def _current_boundary_generation() -> int:
    with _boundary_generation_lock:
        return _boundary_generation


def _advance_boundary_generation() -> int:
    global _boundary_generation
    with _boundary_generation_lock:
        _boundary_generation += 1
        return _boundary_generation


def _boundary_runtime(context: dict):
    with _context_lock:
        if "_boundary_source_digest" not in context:
            context["_boundary_source_digest"] = page_digest(context["page"])
        if "_boundary_store" not in context:
            store = BoundaryCorrectionStore()
            context["_boundary_store"] = store
            records = store.page_records(
                source_digest=context["_boundary_source_digest"],
                page_number=int(context["page_number"]),
                threshold=int(context["threshold"]),
            )
            print(
                f"review: radgränscache: {len(records)} verifierade korrigeringar för sidan",
                flush=True,
            )
        return context["_boundary_store"], context["_boundary_source_digest"]


def _page_records(context: dict) -> list[dict]:
    store, digest = _boundary_runtime(context)
    return store.page_records(
        source_digest=digest,
        page_number=int(context["page_number"]),
        threshold=int(context["threshold"]),
    )


def _mark_strict_boundaries(row_map: dict, records: list[dict]) -> None:
    """Mark proven cuts so the normal ±1 crop pad cannot cross them."""
    columns = row_map.get("columns") or []
    for record in records:
        column = int(record.get("column", -1))
        upper_row = int(record.get("upper_row", -1))
        if not 0 <= column < len(columns):
            continue
        rows = columns[column].get("rows") or []
        if not 0 <= upper_row < len(rows) - 1:
            continue
        rows[upper_row]["_glyph_proven_strict_bottom"] = True
        rows[upper_row + 1]["_glyph_proven_strict_top"] = True


def _row_crop_box_with_strict_boundaries(row: dict, **kwargs):
    """Keep ordinary padding except across a proven horizontal cut."""
    left, top, right, bottom = _original_row_crop_box(row, **kwargs)
    if row.get("_glyph_proven_strict_top"):
        top = max(top, int(row["page_top"]))
    if row.get("_glyph_proven_strict_bottom"):
        bottom = min(bottom, int(row["page_bottom"]))
    return left, top, right, bottom


def _effective_context(context: dict) -> tuple[dict, list[dict]]:
    records = _page_records(context)
    if not records:
        return context, []
    effective = dict(context)
    effective["row_map"] = apply_boundary_corrections(context["row_map"], records)
    _mark_strict_boundaries(effective["row_map"], records)
    return effective, records


def _records_for_row(records: list[dict], column: int, row_index: int) -> list[dict]:
    return [
        record
        for record in records
        if int(record.get("column", -1)) == int(column)
        and row_index in {int(record.get("upper_row", -99)), int(record.get("lower_row", -99))}
    ]


def _candidate_boundaries_for_edge(side: str | None, row_index: int, row_count: int) -> list[int]:
    result = []
    if side in {"top", "both"} and row_index > 0:
        result.append(row_index - 1)
    if side in {"bottom", "both"} and row_index + 1 < row_count:
        result.append(row_index)
    return result


def _gap_boundaries_around_row(rows: list[dict], row_index: int) -> list[int]:
    """Return adjacent row pairs whose preliminary geometry leaves a gap/overlap.

    These pairs must be normalized before glyph review.  Otherwise ink that lies
    in the physical gap is owned by neither row and can never appear as an edge
    residual, which is exactly the failure mode this helper prevents.
    """
    result: list[int] = []
    for upper_row in (row_index - 1, row_index):
        if not 0 <= upper_row < len(rows) - 1:
            continue
        upper = rows[upper_row]
        lower = rows[upper_row + 1]
        if int(upper["page_bottom"]) != int(lower["page_top"]):
            result.append(upper_row)
    return result


def _stamp_generation(state: dict) -> dict:
    state["row_boundary_generation"] = _current_boundary_generation()
    return state


def _prove_existing_boundary(
    context: dict,
    row_map: dict,
    column: int,
    upper_row: int,
    models,
    *,
    digest: str,
) -> dict | None:
    """Prove that the nominal cut is right but the review padding crosses it."""
    columns = row_map.get("columns") or []
    if not 0 <= column < len(columns):
        return None
    rows = columns[column].get("rows") or []
    if not 0 <= upper_row < len(rows) - 1:
        return None
    upper = rows[upper_row]
    lower = rows[upper_row + 1]
    old_upper_bottom = int(upper["page_bottom"])
    old_lower_top = int(lower["page_top"])
    boundary = int(round((old_upper_bottom + old_lower_top) / 2.0))

    strict = evaluate_boundary(
        context["page"],
        row_map,
        column,
        upper_row,
        boundary,
        models,
        threshold=int(context["threshold"]),
    )
    if not (strict["upper"]["fully_exact"] and strict["lower"]["fully_exact"]):
        return None

    upper_padded = _original_load_review_state(
        {**context, "row_map": row_map}, (column, upper_row), models
    )
    lower_padded = _original_load_review_state(
        {**context, "row_map": row_map}, (column, upper_row + 1), models
    )
    upper_unmatched = int(upper_padded.get("source_pixels") or 0) - int(upper_padded.get("covered_pixels") or 0)
    lower_unmatched = int(lower_padded.get("source_pixels") or 0) - int(lower_padded.get("covered_pixels") or 0)
    before_unmatched = upper_unmatched + lower_unmatched
    if before_unmatched <= 0:
        return None

    return {
        "status": "accepted-glyph-proven-existing-horizontal-boundary",
        "page": int(context["page_number"]),
        "column": int(column),
        "upper_row": int(upper_row),
        "lower_row": int(upper_row) + 1,
        "threshold": int(context["threshold"]),
        "source_digest": digest,
        "original_upper_bottom": old_upper_bottom,
        "original_lower_top": old_lower_top,
        "original_boundary": boundary,
        "corrected_boundary": boundary,
        "shift": 0,
        "max_shift": 4,
        "before": {
            "unmatched": before_unmatched,
            "covered": int(upper_padded.get("covered_pixels") or 0) + int(lower_padded.get("covered_pixels") or 0),
            "upper_unmatched": upper_unmatched,
            "lower_unmatched": lower_unmatched,
        },
        "after": {
            "unmatched": 0,
            "covered": strict["covered"],
            "upper_unmatched": 0,
            "lower_unmatched": 0,
        },
        "evidence_facit_digest": model_digest(models),
    }


def _store_and_reanalyse(
    context: dict,
    position: tuple[int, int],
    models,
    correction: dict,
    *,
    store: BoundaryCorrectionStore,
) -> dict:
    store.put(correction)
    generation = _advance_boundary_generation()
    column, row_index = position
    if correction.get("status") == "accepted-blank-row-horizontal-boundary":
        detail = (
            f"vit rasterrad {correction['blank_row_top']}..{correction['blank_row_bottom']}; "
            "facit-oberoende"
        )
    else:
        verb = "verifierad" if int(correction.get("shift", 0)) == 0 else "korrigerad"
        detail = (
            f"{verb}; oförklarat {correction['before']['unmatched']} -> "
            f"{correction['after']['unmatched']}"
        )
    print(
        f"review: radgräns {column}:{correction['upper_row']}/{correction['lower_row']}: "
        f"{correction['original_boundary']} -> {correction['corrected_boundary']} ({detail}); "
        f"cachad, boundary generation {generation}",
        flush=True,
    )

    effective, records = _effective_context(context)
    state = _original_load_review_state(effective, position, models)
    state["row_boundary_corrections"] = _records_for_row(records, column, row_index)
    state["row_boundary_correction_learned"] = correction
    return _stamp_generation(state)


def load_review_state_with_cached_boundaries(context: dict, position: tuple[int, int], models) -> dict:
    """Apply cached cuts and conservatively learn missing straight boundaries.

    Physical gaps between preliminary rows are checked for a full-width white
    separator *before* glyph review.  This is important: ink sitting in such a
    gap otherwise belongs to neither crop and therefore cannot create an edge
    residual that would trigger the old fallback.
    """
    effective, records = _effective_context(context)
    column, row_index = position
    rows = (effective.get("row_map", {}).get("columns") or [])[column].get("rows") or []
    store, digest = _boundary_runtime(context)

    # First normalize any preliminary physical gap/overlap adjacent to this row.
    # This does not depend on facit and therefore must happen before we decide
    # whether the row itself has a glyph residual.
    for upper_row in _gap_boundaries_around_row(rows, row_index):
        existing = store.get(
            source_digest=digest,
            page_number=int(context["page_number"]),
            threshold=int(context["threshold"]),
            column=column,
            upper_row=upper_row,
        )
        if existing is not None:
            continue
        correction = find_blank_row_boundary(
            context["page"],
            effective["row_map"],
            column,
            upper_row,
            threshold=int(context["threshold"]),
            max_shift=4,
            source_digest_value=digest,
            page_number=int(context["page_number"]),
        )
        if correction is None:
            continue
        print(
            f"review: fysisk lucka {column}:{upper_row}/{upper_row + 1}; "
            f"säker fullbredds vit rasterrad y={correction['blank_row_top']}..{correction['blank_row_bottom']}, "
            "flyttar hela ägargränsen innan glyphanalys",
            flush=True,
        )
        return _store_and_reanalyse(
            context,
            position,
            models,
            correction,
            store=store,
        )

    state = _original_load_review_state(effective, position, models)
    state["row_boundary_corrections"] = _records_for_row(records, column, row_index)

    edge_side = ultrafast._residual_edge_side(state)
    if edge_side is None:
        return _stamp_generation(state)

    learned = None
    for upper_row in _candidate_boundaries_for_edge(edge_side, row_index, len(rows)):
        existing = store.get(
            source_digest=digest,
            page_number=int(context["page_number"]),
            threshold=int(context["threshold"]),
            column=column,
            upper_row=upper_row,
        )
        if existing is not None:
            continue

        correction = find_blank_row_boundary(
            context["page"],
            effective["row_map"],
            column,
            upper_row,
            threshold=int(context["threshold"]),
            max_shift=4,
            source_digest_value=digest,
            page_number=int(context["page_number"]),
        )

        if correction is None:
            print(
                f"review: oförklarad kant vid kolumn {column}, rad {row_index}; "
                f"ingen säker vit rasterrad, provar glyphgräns {upper_row}/{upper_row + 1} ±4 px ...",
                flush=True,
            )
            correction = find_boundary_correction(
                context["page"],
                effective["row_map"],
                column,
                upper_row,
                models,
                threshold=int(context["threshold"]),
                max_shift=4,
                source_digest_value=digest,
                page_number=int(context["page_number"]),
            )
            if correction is None:
                correction = _prove_existing_boundary(
                    context,
                    effective["row_map"],
                    column,
                    upper_row,
                    models,
                    digest=digest,
                )
        else:
            print(
                f"review: radgräns {column}:{upper_row}/{upper_row + 1}: "
                f"säker fullbredds vit rasterrad y={correction['blank_row_top']}..{correction['blank_row_bottom']}; "
                "facit behövs inte",
                flush=True,
            )

        if correction is None:
            print(
                f"review: radgräns {column}:{upper_row}/{upper_row + 1}: inget entydigt gränsbevis",
                flush=True,
            )
            continue

        learned = correction
        break

    if learned is None:
        return _stamp_generation(state)

    return _store_and_reanalyse(
        context,
        position,
        models,
        learned,
        store=store,
    )


class BoundaryAwareStateCache(_original_state_cache):
    """Reject any row state computed before the latest learned boundary."""

    def _cached(self, position: tuple[int, int], *, allow_stale_exact: bool) -> dict | None:
        state = super()._cached(position, allow_stale_exact=allow_stale_exact)
        if state is None:
            return None
        if int(state.get("row_boundary_generation", -1)) != _current_boundary_generation():
            return None
        return state


def diagnostic_text_with_boundaries(state: dict) -> str:
    text = _original_diagnostic_text(state)
    records = state.get("row_boundary_corrections") or []
    learned = state.get("row_boundary_correction_learned")
    if not records and not learned:
        return text

    insert = []
    if records:
        insert.append("row_boundary_corrections:")
        for record in records:
            insert.append("  " + json.dumps(record, ensure_ascii=False, sort_keys=True))
    if learned:
        insert.append("row_boundary_correction_learned:")
        insert.append("  " + json.dumps(learned, ensure_ascii=False, sort_keys=True))
    marker = "items:\n"
    payload = "\n".join(insert) + "\n"
    if marker in text:
        return text.replace(marker, payload + marker, 1)
    return text + payload


fast._row_crop_box = _row_crop_box_with_strict_boundaries
fast.load_review_state_fast = load_review_state_with_cached_boundaries
fast.SynchronizedStateCache = BoundaryAwareStateCache
ultrafast.diagnostic_text = diagnostic_text_with_boundaries


def main() -> int:
    print("review: BOUNDARY använder ULTRAFAST + cachade raka radgränser", flush=True)
    print("review: fysisk lucka mellan rader provas med fullbredds vit rasterrad före glyphanalys", flush=True)
    print("review: vid kantresidual provas också fullbredds vit rasterrad, helt utan facit", flush=True)
    print("review: bara om vitlinjeregeln inte avgör körs den dyrare glyphgränssökningen ±4 px", flush=True)
    print("review: en redan rätt gräns kan också verifieras med glyphbevis och shift 0", flush=True)
    print("review: verifierad gräns är strikt: ±1 crop-padding får inte korsa den", flush=True)
    print("review: lyckad korrigering/verifiering sparas i data/generated/ocr-page-cache/row-boundary-corrections-v1.json", flush=True)
    print("review: ny gräns gör gamla radanalyser stale så båda grannraderna räknas om", flush=True)
    print("review: utan entydigt gränsbevis lämnas residualpixlarna till glyph-editorn", flush=True)
    return ultrafast.main()


if __name__ == "__main__":
    raise SystemExit(main())
