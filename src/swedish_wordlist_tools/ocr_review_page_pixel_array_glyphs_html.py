from __future__ import annotations

"""Glyph review backed by one page-wide byte ownership array."""

import threading
import time

from . import ocr_review_five_rows_glyphs_ultrafast_html as ultrafast
from .ocr_neighbor_row_raster import add_neighbor_row_raster
from .ocr_page_pixel_array import PagePixelArray
from .ocr_refine_known_glyph_ownership import refine_known_glyph_ownership


fast = ultrafast.fast
_current_pixel_context: dict | None = None


def _timed(label: str, started: float) -> None:
    print(f"review: tid {label}: {time.perf_counter() - started:.3f} s", flush=True)


def build_page_context_pixel_array(jsonl, page_number: int, threshold: int = 210) -> dict:
    """Load/segment/threshold one page, with startup timing for every major step."""
    global _current_pixel_context
    total_started = time.perf_counter()
    print(f"review: laddar sida {page_number} och segmenterar geometri en gång ...", flush=True)

    started = time.perf_counter()
    # read_jsonl is a generator and source_for_page returns immediately on the
    # first exact SAOL14_XXXXX.png hit.  Do not materialise the complete JSONL.
    source = fast.source_for_page(fast.read_jsonl(jsonl), page_number)
    _timed("JSONL -> sidkälla", started)
    if not source:
        raise ValueError(f"no source found for page {page_number}")

    started = time.perf_counter()
    page = fast._load_source_image(source)
    _timed("PNG-inläsning", started)
    if page is None:
        raise ValueError(f"could not load page image: {source}")

    started = time.perf_counter()
    row_map = fast.segment_page_rows(page, threshold=threshold)
    positions = [
        (column, row_index)
        for column, column_entry in enumerate(row_map["columns"])
        for row_index, _row in enumerate(column_entry.get("rows") or [])
    ]
    _timed("sid-/radgeometri", started)
    print(f"review: geometri klar: {len(positions)} rader", flush=True)

    context = {
        "source": source,
        "page": page,
        "row_map": row_map,
        "positions": positions,
        "threshold": threshold,
        "page_number": page_number,
    }

    started = time.perf_counter()
    gray_page = page if page.mode == "L" else page.convert("L")
    owners = PagePixelArray.from_image(gray_page, threshold=threshold)
    _timed("gråskala + threshold", started)

    started = time.perf_counter()
    ignored_regions = owners.mask_dense_black_rectangles()
    assigned = owners.assign_row_map(row_map)
    _timed("initialt pixelägande", started)

    context["pixel_owners"] = owners
    context["pixel_gray_page"] = gray_page
    context["ignored_black_rectangles"] = ignored_regions
    context["known_glyph_ownership_refinements"] = []
    context["known_glyph_ownership_done_pairs"] = set()
    context["known_glyph_ownership_lock"] = threading.Lock()
    context["pixel_owner_revision"] = 0

    started = time.perf_counter()
    content_lefts: dict[int, int | None] = {}
    for column_index, column_entry in enumerate(row_map.get("columns") or []):
        rule_x = fast._persistent_left_rule_x(gray_page, column_entry, threshold=threshold)
        content_lefts[column_index] = rule_x + 2 if rule_x is not None else None
    context["column_content_lefts"] = content_lefts
    _timed("kolumngeometri", started)

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
    _timed("sidförberedelse totalt", total_started)
    _current_pixel_context = context
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
    column_index, upper_row_index = pair
    columns = context["row_map"].get("columns") or []
    if not 0 <= column_index < len(columns):
        return None
    column = columns[column_index]
    rows = column.get("rows") or []
    if not 0 <= upper_row_index < len(rows) - 1:
        return None
    y = int(rows[upper_row_index]["page_bottom"])
    owners: PagePixelArray = context["pixel_owners"]
    left = max(0, int(column.get("crop_left", column.get("left", 0))))
    content_left = (context.get("column_content_lefts") or {}).get(column_index)
    if content_left is not None:
        left = max(left, int(content_left))
    right = min(owners.width, int(column.get("crop_right", column.get("right", owners.width))))
    if right <= left:
        return None
    return y, left, right


def _pair_has_ink_bridge(context: dict, pair: tuple[int, int]) -> bool:
    geometry = _pair_boundary(context, pair)
    if geometry is None:
        return False
    y, left, right = geometry
    owners: PagePixelArray = context["pixel_owners"]
    return owners.boundary_bridge_count(y, left=left, right=right) > 0


def _ensure_known_glyph_ownership(context: dict, pairs: set[tuple[int, int]], models) -> bool:
    """Refine requested boundaries once; bump ownership revision on real moves."""
    if not pairs:
        return False
    changed_any = False
    lock = context["known_glyph_ownership_lock"]
    with lock:
        done = context["known_glyph_ownership_done_pairs"]
        pending = pairs - done
        if not pending:
            return False
        done.update(pending)
        for pair in sorted(pending):
            if not _pair_has_ink_bridge(context, pair):
                continue
            print(
                f"review: bläck korsar geometrisk radgräns "
                f"c{pair[0]} r{pair[1]}/r{pair[1] + 1}; analyserar glyphägande ...",
                flush=True,
            )
            started = time.perf_counter()
            changes = refine_known_glyph_ownership(
                context["pixel_gray_page"],
                context["row_map"],
                context["pixel_owners"],
                models,
                threshold=context["threshold"],
                pairs={pair},
            )
            moved = sum(
                int(change.get("moved_to_upper") or 0) + int(change.get("moved_to_lower") or 0)
                for change in changes
            )
            if moved:
                changed_any = True
                context["pixel_owner_revision"] = int(context.get("pixel_owner_revision") or 0) + 1
            context["known_glyph_ownership_refinements"].extend(changes)
            print(
                f"review: glyphägande c{pair[0]} r{pair[1]}/r{pair[1] + 1} "
                f"klart på {time.perf_counter() - started:.3f} s; revision={context['pixel_owner_revision']}",
                flush=True,
            )
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
    return changed_any


def _load_owned_row_state(context: dict, position: tuple[int, int], models) -> dict:
    """Analyse one row from a stable snapshot of the current ownership raster."""
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
    content_left = (context.get("column_content_lefts") or {}).get(column)
    box = fast._row_crop_box(
        row,
        column=column,
        page_width=page.width,
        page_height=page.height,
        pad_y=4,
        left_override=content_left,
    )

    # Snapshot the owner-filtered crop under the same short lock used for owner
    # mutation.  Exact matching itself runs outside the lock and stays parallel.
    with context["known_glyph_ownership_lock"]:
        owner_revision = int(context.get("pixel_owner_revision") or 0)
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
        items.append({
            "id": item_id, "kind": "match", "label": match.label,
            "style": match.style, "pixels": len(points), "bbox": fast.legacy._bbox(set(points)),
        })
    for index, points in enumerate(residuals):
        item_id = f"U{index:02d}"
        point_sets[item_id] = points
        items.append({
            "id": item_id, "kind": "residual", "label": "?", "style": "unknown",
            "pixels": len(points), "bbox": fast.legacy._bbox(set(points)),
        })

    return {
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
        "pixel_owner_revision": owner_revision,
        "pixel_array_counts": owners.counts(),
        "ignored_black_rectangles": context.get("ignored_black_rectangles") or [],
        "known_glyph_ownership_refinements": context.get("known_glyph_ownership_refinements") or [],
    }


def load_review_state_pixel_array(context: dict, position: tuple[int, int], models) -> dict:
    state = _load_owned_row_state(context, position, models)
    if not state["fully_exact"]:
        changed = _ensure_known_glyph_ownership(context, _neighbor_pairs(context, position), models)
        if changed or state["pixel_owner_revision"] != int(context.get("pixel_owner_revision") or 0):
            state = _load_owned_row_state(context, position, models)
    return add_neighbor_row_raster(context, state, probe_y=8)


# The five-row cache can compute neighbouring rows concurrently.  Ownership can
# change while those futures are running, so reject states produced from an old
# page-ownership revision before the packet is rendered.
_original_cache_get_many = fast.SynchronizedStateCache.get_many


def _get_many_owner_revision_safe(self, positions):
    states = _original_cache_get_many(self, positions)
    context = _current_pixel_context
    if context is None:
        return states
    current = int(context.get("pixel_owner_revision") or 0)
    out = []
    for position, state in zip(positions, states):
        revision = state.get("pixel_owner_revision")
        if revision is not None and int(revision) != current:
            self.invalidate(position)
            state = self.get(position)
        out.append(state)
    return out


fast.SynchronizedStateCache.get_many = _get_many_owner_revision_safe


# ULTRAFAST's renderer paints all guides red.  Keep its UI but make support
# lines blue and persist the three-row checkbox across normal row navigation.
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
    document = document.replace(old, new, 1)

    old_toggle = """  checkbox.addEventListener('change',()=>{wrap.style.display=checkbox.checked?'block':'none';if(checkbox.checked)drawNeighbor();});
  nimg.onload=()=>{if(checkbox.checked)drawNeighbor();};"""
    new_toggle = """  const neighborStorageKey='saolGlyphReview.showNeighbors';
  try { checkbox.checked=localStorage.getItem(neighborStorageKey)==='1'; } catch(_err) {}
  wrap.style.display=checkbox.checked?'block':'none';
  checkbox.addEventListener('change',()=>{
    wrap.style.display=checkbox.checked?'block':'none';
    try { localStorage.setItem(neighborStorageKey,checkbox.checked?'1':'0'); } catch(_err) {}
    if(checkbox.checked)drawNeighbor();
  });
  nimg.onload=()=>{if(checkbox.checked)drawNeighbor();};"""
    if old_toggle not in document:
        raise ValueError("could not find three-row toggle renderer")
    return document.replace(old_toggle, new_toggle, 1)


fast.ui.editor.render_html = _render_html_with_blue_support_lines


def main() -> int:
    fast.build_page_context = build_page_context_pixel_array
    fast.load_review_state_fast = load_review_state_pixel_array
    print("review: BYTE-ARRAY använder en sidglobal raster; PNG/threshold görs en gång", flush=True)
    print("review: JSONL-sidkälla söks strömmande och starttider loggas per steg", flush=True)
    print("review: normal rad analyseras först; exakt rad triggar aldrig två-raders glyphägande", flush=True)
    print("review: pixelägande revisionsmärks så parallella femradersresultat inte kan bli stale", flush=True)
    print("review: Visa tre rader sparas i webbläsaren mellan radbyten", flush=True)
    print("review: stödlinjer visas en pixel under baseline och alltid i blått", flush=True)
    print("review: stora täta svarta bokstavsrektanglar maskas helt före radägande", flush=True)
    return fast.main()


if __name__ == "__main__":
    raise SystemExit(main())
