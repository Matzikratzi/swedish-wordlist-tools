from __future__ import annotations

import json
import threading

from . import ocr_review_five_rows_glyphs_ultrafast_html as ultrafast
from .ocr_row_boundary_corrections import (
    BoundaryCorrectionStore,
    apply_boundary_corrections,
    find_boundary_correction,
    page_digest,
)


fast = ultrafast.fast
_original_load_review_state = fast.load_review_state_fast
_original_diagnostic_text = ultrafast.diagnostic_text
_context_lock = threading.RLock()


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


def _effective_context(context: dict) -> tuple[dict, list[dict]]:
    records = _page_records(context)
    if not records:
        return context, []
    effective = dict(context)
    effective["row_map"] = apply_boundary_corrections(context["row_map"], records)
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


def load_review_state_with_cached_boundaries(context: dict, position: tuple[int, int], models) -> dict:
    """Apply learned cuts, and learn a new one only for edge residuals.

    The ordinary segmentation remains untouched. A copied row map gets cached
    horizontal corrections, so concurrent row analyses never observe a temporary
    mutation of the shared geometry.
    """
    effective, records = _effective_context(context)
    state = _original_load_review_state(effective, position, models)
    column, row_index = position
    state["row_boundary_corrections"] = _records_for_row(records, column, row_index)

    edge_side = ultrafast._residual_edge_side(state)
    if edge_side is None:
        return state

    rows = (effective.get("row_map", {}).get("columns") or [])[column].get("rows") or []
    store, digest = _boundary_runtime(context)
    learned = None
    for upper_row in _candidate_boundaries_for_edge(edge_side, row_index, len(rows)):
        # Never repeatedly optimize a boundary already proven and cached. If a
        # residual remains after that cut, it belongs in the glyph editor.
        existing = store.get(
            source_digest=digest,
            page_number=int(context["page_number"]),
            threshold=int(context["threshold"]),
            column=column,
            upper_row=upper_row,
        )
        if existing is not None:
            continue

        print(
            f"review: oförklarad kant vid kolumn {column}, rad {row_index}; "
            f"provar rak gräns {upper_row}/{upper_row + 1} ±4 px ...",
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
            print(
                f"review: radgräns {column}:{upper_row}/{upper_row + 1}: inget entydigt glyphbevis",
                flush=True,
            )
            continue

        store.put(correction)
        learned = correction
        print(
            f"review: radgräns {column}:{upper_row}/{upper_row + 1}: "
            f"{correction['original_boundary']} -> {correction['corrected_boundary']} "
            f"(oförklarat {correction['before']['unmatched']} -> {correction['after']['unmatched']}); cachad",
            flush=True,
        )
        break

    if learned is None:
        return state

    effective, records = _effective_context(context)
    state = _original_load_review_state(effective, position, models)
    state["row_boundary_corrections"] = _records_for_row(records, column, row_index)
    state["row_boundary_correction_learned"] = learned
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


fast.load_review_state_fast = load_review_state_with_cached_boundaries
# ultrafast.render_html_with_neighbor_raster resolves this global at call time.
ultrafast.diagnostic_text = diagnostic_text_with_boundaries


def main() -> int:
    print("review: BOUNDARY använder ULTRAFAST + cachade glyphbevisade raka radgränser", flush=True)
    print("review: vanliga radgränser lämnas orörda; fallback körs bara för kantresidualer", flush=True)
    print("review: gränssökning är ±4 px och måste förbättra båda rader utan försämring", flush=True)
    print("review: lyckad korrigering sparas i data/generated/ocr-page-cache/row-boundary-corrections-v1.json", flush=True)
    print("review: misslyckad/ambiguous korrigering lämnar residualpixlarna till glyph-editorn", flush=True)
    return ultrafast.main()


if __name__ == "__main__":
    raise SystemExit(main())
