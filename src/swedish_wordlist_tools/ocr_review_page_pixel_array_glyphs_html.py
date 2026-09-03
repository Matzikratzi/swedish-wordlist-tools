from __future__ import annotations

"""Experimental glyph review backed by one page-wide byte ownership array.

This deliberately leaves the existing review implementation intact. The page
is thresholded once into ``PagePixelArray`` and physical row geometry assigns
black source pixels to rows. Review crops may still include the familiar +/-1
vertical context, but only pixels owned by the target row are rendered into the
image passed to the exact glyph matcher.

The mature ULTRAFAST editor chrome is reused, including the unfiltered
three-row source raster and the paste-friendly diagnostic export. Those views
are diagnostics only: glyph matching still receives the owner-filtered byte
array crop.
"""

import threading

from . import ocr_review_five_rows_glyphs_ultrafast_html as ultrafast
from .ocr_neighbor_row_raster import add_neighbor_row_raster
from .ocr_page_pixel_array import PagePixelArray, WHITE
from .ocr_refine_known_glyph_ownership import refine_known_glyph_ownership


fast = ultrafast.fast
_original_build_page_context = fast.build_page_context


def build_page_context_pixel_array(jsonl, page_number: int, threshold: int = 210) -> dict:
    context = _original_build_page_context(jsonl, page_number, threshold)

    # Keep one grayscale page for all later boundary probes and glyph crops.
    # PagePixelArray consumes the same raster, so the audit path does not keep
    # converting the complete PNG for each row boundary.
    gray_page = context["page"] if context["page"].mode == "L" else context["page"].convert("L")
    owners = PagePixelArray.from_image(gray_page, threshold=threshold)

    # SAOL's section-letter marker is a large dense black rectangle containing
    # white upper/lower case letters. It is page furniture, not body-text ink:
    # mask its entire rectangle before any row can claim pixels from it.
    ignored_regions = owners.mask_dense_black_rectangles()
    assigned = owners.assign_row_map(context["row_map"])
    context["pixel_owners"] = owners
    context["pixel_gray_page"] = gray_page
    context["ignored_black_rectangles"] = ignored_regions
    context["known_glyph_ownership_refinements"] = []
    context["known_glyph_ownership_done_pairs"] = set()
    context["known_glyph_ownership_lock"] = threading.Lock()
    counts = owners.counts()
    if ignored_regions:
        for region in ignored_regions:
            print(
                "review: ignorerar svart bokstavsrektangel "
                f"box={region['box']}, {region['masked_ink_pixels']} svarta pixlar",
                flush=True,
            )
    print(
        "review: byte-array: "
        f"{assigned} svarta pixlar radtilldelade, "
        f"{counts['unassigned_ink']} svarta pixlar ännu otilldelade",
        flush=True,
    )
    return context


def _neighbor_pairs(context: dict, position: tuple[int, int]) -> set[tuple[int, int]]:
    column, row_index = position
    columns = context["row_map"].get("columns") or []
    if not 0 <= column < len(columns):
        return set()
    row_count = len(columns[column].get("rows") or [])
    pairs: set[tuple[int, int]] = set()
    if row_index > 0:
        pairs.add((column, row_index - 1))
    if row_index + 1 < row_count:
        pairs.add((column, row_index))
    return pairs


def _pair_boundary(context: dict, pair: tuple[int, int]) -> tuple[int, int, int] | None:
    """Return (y, left, right) for the provisional separator of one row pair."""
    column_index, upper_row_index = pair
    columns = context["row_map"].get("columns") or []
    if not 0 <= column_index < len(columns):
        return None
    column = columns[column_index]
    rows = column.get("rows") or []
    if not 0 <= upper_row_index < len(rows) - 1:
        return None
    upper = rows[upper_row_index]
    lower = rows[upper_row_index + 1]
    y = (int(upper["page_bottom"]) + int(lower["page_top"])) // 2
    left = max(0, int(column.get("crop_left", column.get("left", 0))))
    right = min(
        context["pixel_owners"].width,
        int(column.get("crop_right", column.get("right", context["pixel_owners"].width))),
    )
    if right <= left:
        return None
    return y, left, right


def _pair_has_ink_bridge(context: dict, pair: tuple[int, int]) -> bool:
    """Cheap byte-array test before any exact-glyph analysis.

    A normal PDF-rendered row boundary is a clean separator. If no black source
    pixel above the provisional split is 8-connected to black source ink below
    it, there is nothing for the expensive two-baseline glyph matcher to solve.
    The test uses the already-thresholded page bytes and therefore does no PIL
    conversion and no glyph matching.
    """
    geometry = _pair_boundary(context, pair)
    if geometry is None:
        return False
    y, left, right = geometry
    owners: PagePixelArray = context["pixel_owners"]
    if not 0 < y < owners.height:
        return False

    upper_start = (y - 1) * owners.width
    lower_start = y * owners.width
    data = owners.data
    for x in range(left, right):
        if data[upper_start + x] == WHITE:
            continue
        for nx in (x - 1, x, x + 1):
            if left <= nx < right and data[lower_start + nx] != WHITE:
                return True
    return False


def _ensure_known_glyph_ownership(context: dict, position: tuple[int, int], models) -> None:
    """Refine only genuinely touching boundaries adjacent to the displayed row.

    Most row separators in the PDF-rendered pages are trivial. They are rejected
    by a tiny byte-array connectivity probe. Only a boundary where source ink is
    actually connected across the provisional split reaches the expensive exact
    glyph analysis, and every pair is considered at most once.
    """
    wanted = _neighbor_pairs(context, position)
    if not wanted:
        return
    lock = context["known_glyph_ownership_lock"]
    with lock:
        done = context["known_glyph_ownership_done_pairs"]
        pending = wanted - done
        if not pending:
            return
        done.update(pending)
        for pair in sorted(pending):
            if not _pair_has_ink_bridge(context, pair):
                continue
            print(
                f"review: sammanvuxen radgräns c{pair[0]} r{pair[1]}/r{pair[1] + 1}; analyserar glyphägande ...",
                flush=True,
            )
            changes = refine_known_glyph_ownership(
                context["pixel_gray_page"],
                context["row_map"],
                context["pixel_owners"],
                models,
                threshold=context["threshold"],
                pairs={pair},
            )
            context["known_glyph_ownership_refinements"].extend(changes)
            for change in changes:
                print(
                    "review: glyphägande "
                    f"c{change['column']} r{change['upper_row']}/r{change['lower_row']} "
                    f"y={change['boundary']} "
                    f"övre={change['upper_labels']!r} undre={change['lower_labels']!r} "
                    f"flyttade={change['moved_to_upper']}/{change['moved_to_lower']} "
                    f"konflikt={change['conflict_pixels']}",
                    flush=True,
                )


def load_review_state_pixel_array(context: dict, position: tuple[int, int], models) -> dict:
    _ensure_known_glyph_ownership(context, position, models)

    column, row_index = position
    page = context["page"]
    row_map = context["row_map"]
    threshold = context["threshold"]
    owners: PagePixelArray = context["pixel_owners"]
    column_entry = row_map["columns"][column]
    physical_rows = column_entry.get("rows") or []
    if not 0 <= row_index < len(physical_rows):
        raise ValueError(f"row {row_index} out of range; column {column} has {len(physical_rows)} rows")
    row = physical_rows[row_index]

    rule_x = fast._persistent_left_rule_x(page, column_entry, threshold=threshold)
    content_left = rule_x + 2 if rule_x is not None else None
    box = fast._row_crop_box(
        row,
        column=column,
        page_width=page.width,
        page_height=page.height,
        pad_y=1,
        left_override=content_left,
    )

    crop = owners.render_owner_crop(row_index=row_index, box=box)
    crop, trimmed_left = fast.legacy._trim_leading_white_columns(crop, threshold=threshold, keep=2)
    if trimmed_left:
        box = (box[0] + trimmed_left, box[1], box[2], box[3])

    result = fast.analyse_row_exact(crop, models, threshold=threshold)
    selected = result["selected"]
    covered = set().union(*(match.pixels for match in selected)) if selected else set()
    residual = result["ink"] - covered
    residuals = fast.residual_component_pixels(residual)

    items = []
    point_sets: dict[str, frozenset[tuple[int, int]]] = {}
    for index, match in enumerate(selected):
        item_id = f"M{index:02d}"
        points = frozenset(match.pixels)
        point_sets[item_id] = points
        items.append(
            {
                "id": item_id,
                "kind": "match",
                "label": match.label,
                "style": match.style,
                "pixels": len(points),
                "bbox": fast.legacy._bbox(set(points)),
            }
        )
    for index, points in enumerate(residuals):
        item_id = f"U{index:02d}"
        point_sets[item_id] = points
        items.append(
            {
                "id": item_id,
                "kind": "residual",
                "label": "?",
                "style": "unknown",
                "pixels": len(points),
                "bbox": fast.legacy._bbox(set(points)),
            }
        )

    state = {
        "source": context["source"],
        "page": context["page_number"],
        "column": column,
        "row": row_index,
        "row_page_top": int(row["page_top"]),
        "row_page_bottom": int(row["page_bottom"]),
        "crop_box": box,
        "crop_width": crop.width,
        "crop_height": crop.height,
        "image": fast.legacy._png_data_uri(crop),
        "baseline": result["baseline"],
        "covered_pixels": result["covered_pixels"],
        "source_pixels": result["source_pixels"],
        "source_ink_points": [[x, y] for x, y in sorted(result["ink"])],
        "removed_neighbor_pixels": 0,
        "two_row_removed_pixels": 0,
        "fully_exact": result["fully_exact"],
        "text": fast.render_exact_text(selected, source_ink=result["ink"]) if selected else "",
        "markup": fast.render_exact_markup(selected, source_ink=result["ink"]) if selected else "",
        "items": items,
        "point_sets": point_sets,
        "matches": selected,
        "pixel_owner_mode": "page-byte-array+known-glyphs",
        "pixel_owner_code": PagePixelArray.row_code(row_index),
        "pixel_array_counts": owners.counts(),
        "ignored_black_rectangles": context.get("ignored_black_rectangles") or [],
        "known_glyph_ownership_refinements": context.get("known_glyph_ownership_refinements") or [],
    }

    return add_neighbor_row_raster(context, state, probe_y=8)


# ULTRAFAST's mature neighbour renderer predates the distinction between row
# separators and support guides and therefore paints every guide red. Keep the
# renderer itself intact, but make STÖDLINJE blue in this byte-array editor.
_original_editor_render_html = fast.ui.editor.render_html


def _render_html_with_blue_support_lines(state, message=""):
    document = _original_editor_render_html(state, message)
    old = """    ctx.save();ctx.strokeStyle='rgba(190,25,25,.95)';ctx.lineWidth=2;
    const boundaries=S.neighbor_row_boundaries || [[S.neighbor_core_top,'target top'],[S.neighbor_core_bottom,'target bottom']];
    for(const entry of boundaries){
      const yy=entry[0], label=entry[1];
      const y=ntop+yy*nscale+.5;ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(canvas.width,y);ctx.stroke();
      ctx.fillStyle='rgba(190,25,25,.95)';ctx.font='11px monospace';ctx.fillText(label,4,Math.max(11,y-2));
    }
    ctx.restore();"""
    new = """    ctx.save();ctx.lineWidth=2;
    const boundaries=S.neighbor_row_boundaries || [[S.neighbor_core_top,'target top'],[S.neighbor_core_bottom,'target bottom']];
    for(const entry of boundaries){
      const yy=entry[0], label=entry[1];
      const support=String(label).startsWith('STÖDLINJE');
      const guideColor=support?'rgba(25,90,190,.95)':'rgba(190,25,25,.95)';
      ctx.strokeStyle=guideColor;
      const y=ntop+yy*nscale+.5;ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(canvas.width,y);ctx.stroke();
      ctx.fillStyle=guideColor;ctx.font='11px monospace';ctx.fillText(label,4,Math.max(11,y-2));
    }
    ctx.restore();"""
    if old not in document:
        raise ValueError("could not find three-row guide renderer")
    return document.replace(old, new, 1)


fast.ui.editor.render_html = _render_html_with_blue_support_lines


def main() -> int:
    fast.build_page_context = build_page_context_pixel_array
    fast.load_review_state_fast = load_review_state_pixel_array
    print("review: BYTE-ARRAY använder sidglobalt pixelägande; ingen grannpixel kan läcka via crop-padding", flush=True)
    print("review: rena radgränser avgörs direkt i byte-arrayen; glyphmatchning körs bara vid sammanvuxet bläck", flush=True)
    print("review: kända exakta glyphar får korrigera pixelägande över sammanvuxna radgränser", flush=True)
    print("review: stödlinjer visas en pixel under baseline och alltid i blått", flush=True)
    print("review: stora täta svarta bokstavsrektanglar maskas helt före radägande", flush=True)
    print("review: Visa tre rader och Kopiera diagnostik + raster är åter aktiva som ofiltrerad debug", flush=True)
    return fast.main()


if __name__ == "__main__":
    raise SystemExit(main())
