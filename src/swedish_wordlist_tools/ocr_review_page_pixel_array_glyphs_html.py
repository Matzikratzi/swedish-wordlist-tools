from __future__ import annotations

"""Experimental glyph review backed by one page-wide byte ownership array.

This deliberately leaves the existing review implementation intact.  The page
is thresholded once into ``PagePixelArray`` and physical row geometry assigns
black source pixels to rows.  Review crops may still include the familiar +/-1
vertical context, but only pixels owned by the target row are rendered into the
image passed to the exact glyph matcher.

The mature ULTRAFAST editor chrome is reused, including the unfiltered
three-row source raster and the paste-friendly diagnostic export.  Those views
are diagnostics only: glyph matching still receives the owner-filtered byte
array crop.
"""

from . import ocr_review_five_rows_glyphs_ultrafast_html as ultrafast
from .ocr_neighbor_row_raster import add_neighbor_row_raster
from .ocr_page_pixel_array import PagePixelArray


fast = ultrafast.fast
_original_build_page_context = fast.build_page_context


def build_page_context_pixel_array(jsonl, page_number: int, threshold: int = 210) -> dict:
    context = _original_build_page_context(jsonl, page_number, threshold)
    owners = PagePixelArray.from_image(context["page"], threshold=threshold)

    # SAOL's section-letter marker is a large dense black rectangle containing
    # white upper/lower case letters.  It is page furniture, not body-text ink:
    # mask its entire rectangle before any row can claim pixels from it.
    ignored_regions = owners.mask_dense_black_rectangles()
    assigned = owners.assign_row_map(context["row_map"])
    context["pixel_owners"] = owners
    context["ignored_black_rectangles"] = ignored_regions
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


def load_review_state_pixel_array(context: dict, position: tuple[int, int], models) -> dict:
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

    # Important difference from the old path: the padded rectangle does not
    # decide ownership.  It is merely a viewport over the page-wide byte array.
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
        "pixel_owner_mode": "page-byte-array",
        "pixel_owner_code": PagePixelArray.row_code(row_index),
        "pixel_array_counts": owners.counts(),
        "ignored_black_rectangles": context.get("ignored_black_rectangles") or [],
    }

    # Keep the old editor's three-row view as an *unfiltered* diagnostic view of
    # the source PNG.  It never feeds pixels back into the matcher or ownership.
    return add_neighbor_row_raster(context, state, probe_y=8)


def main() -> int:
    # Importing ULTRAFAST above installs its mature editor decorations: the
    # three-row checkbox and diagnostic-copy button.  Replace only page setup and
    # row raster production so those controls also work in byte-array mode.
    fast.build_page_context = build_page_context_pixel_array
    fast.load_review_state_fast = load_review_state_pixel_array
    print("review: BYTE-ARRAY använder sidglobalt pixelägande; ingen grannpixel kan läcka via crop-padding", flush=True)
    print("review: stora täta svarta bokstavsrektanglar maskas helt före radägande", flush=True)
    print("review: Visa tre rader och Kopiera diagnostik + raster är åter aktiva som ofiltrerad debug", flush=True)
    return fast.main()


if __name__ == "__main__":
    raise SystemExit(main())
