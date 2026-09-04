from __future__ import annotations

import argparse
import json
from collections import deque
from pathlib import Path

from .ocr_column_row_segmentation import segment_page_rows
from .ocr_glyph_matcher import load_facit
from .ocr_prepare_sequential_page import _load_source_image, read_jsonl, source_for_page
from .ocr_probe_row_glyphs import analyse_row_exact
from .ocr_row_map_words import _persistent_left_rule_x, _row_crop_box


def residual_component_pixels(ink: set[tuple[int, int]]) -> list[frozenset[tuple[int, int]]]:
    """Return 8-connected residual components in left-to-right order."""
    remaining = set(ink)
    components: list[frozenset[tuple[int, int]]] = []
    while remaining:
        start = min(remaining, key=lambda point: (point[0], point[1]))
        remaining.remove(start)
        queue = deque([start])
        points = {start}
        while queue:
            x, y = queue.popleft()
            for ny in range(y - 1, y + 2):
                for nx in range(x - 1, x + 2):
                    point = (nx, ny)
                    if point in remaining:
                        remaining.remove(point)
                        queue.append(point)
                        points.add(point)
        components.append(frozenset(points))
    components.sort(
        key=lambda points: (
            min(x for x, _y in points),
            min(y for _x, y in points),
        )
    )
    return components


def parse_glyph_spec(value: str) -> tuple[str, tuple[int, ...]]:
    """Parse LABEL=U00,U01 (the U prefix is optional)."""
    if "=" not in value:
        raise argparse.ArgumentTypeError("glyph must be LABEL=U00[,U01...]")
    label, raw_indices = value.split("=", 1)
    if not label:
        raise argparse.ArgumentTypeError("glyph label may not be empty")
    try:
        indices = tuple(int(item.strip().removeprefix("U")) for item in raw_indices.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("component indices must be U00,U01,...") from exc
    if not indices:
        raise argparse.ArgumentTypeError("at least one residual component is required")
    return label, indices


def glyph_from_components(
    label: str,
    style: str,
    components: list[frozenset[tuple[int, int]]],
    indices: tuple[int, ...],
    baseline: int,
    source: dict,
) -> dict:
    try:
        points = set().union(*(components[index] for index in indices))
    except IndexError as exc:
        raise ValueError(f"residual component index out of range: {indices}") from exc
    left = min(x for x, _y in points)
    normalized = sorted((x - left, y - baseline) for x, y in points)
    return {
        "label": label,
        "style": style,
        "pixels_relative_to_baseline": [[x, y] for x, y in normalized],
        "sources": [source],
    }


def _apply_reviewed_role(payload: dict, glyph: dict) -> None:
    """Persist the editor's reviewed typography choice in v2's active role field.

    The review UI still names the three visual choices ``roman``, ``italic`` and
    ``bold``.  Facit v2 loads ``role`` rather than legacy ``style``.  Keep the
    legacy field for provenance, but make the reviewed choice active as well.
    """
    if payload.get("format") == "saol14-manual-glyph-facit-v2":
        glyph["role"] = glyph.get("style") or "unknown"


def add_or_merge_glyph(payload: dict, glyph: dict) -> str:
    _apply_reviewed_role(payload, glyph)
    key = (
        glyph["label"],
        glyph["style"],
        tuple(tuple(point) for point in glyph["pixels_relative_to_baseline"]),
    )
    for existing in payload.get("glyphs") or []:
        existing_key = (
            existing.get("label"),
            existing.get("style"),
            tuple(tuple(point) for point in existing.get("pixels_relative_to_baseline") or []),
        )
        if existing_key != key:
            continue
        if payload.get("format") == "saol14-manual-glyph-facit-v2":
            # Selecting a concrete visual style in the editor is an explicit
            # review decision. Replace an absent/unknown semantic role so the
            # model is immediately loadable with that reviewed classification.
            if not existing.get("role") or existing.get("role") == "unknown":
                existing["role"] = glyph["role"]
        known = {json.dumps(item, sort_keys=True, ensure_ascii=False) for item in existing.get("sources") or []}
        for source in glyph.get("sources") or []:
            encoded = json.dumps(source, sort_keys=True, ensure_ascii=False)
            if encoded not in known:
                existing.setdefault("sources", []).append(source)
        return "merged"
    payload.setdefault("glyphs", []).append(glyph)
    return "added"


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Add manually identified unmatched row components to the SAOL glyph facit."
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--page", type=int, required=True)
    ap.add_argument("--column", type=int, choices=(0, 1, 2), required=True)
    ap.add_argument("--row", type=int, required=True)
    ap.add_argument("--glyph", action="append", type=parse_glyph_spec, required=True)
    ap.add_argument("--style", default="roman")
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--facit", type=Path, default=Path("glyphs/saol14-manual-glyph-facit.json"))
    args = ap.parse_args()

    jsonl_rows = list(read_jsonl(args.jsonl))
    source_url = source_for_page(jsonl_rows, args.page)
    if not source_url:
        raise SystemExit(f"no source found for page {args.page}")
    page = _load_source_image(source_url)
    if page is None:
        raise SystemExit(f"could not load page image: {source_url}")

    row_map = segment_page_rows(page, threshold=args.threshold)
    column_entry = row_map["columns"][args.column]
    rows = column_entry.get("rows") or []
    if not 0 <= args.row < len(rows):
        raise SystemExit(f"row {args.row} out of range; column {args.column} has {len(rows)} rows")
    row = rows[args.row]
    rule_x = _persistent_left_rule_x(page, column_entry, threshold=args.threshold)
    content_left = rule_x + 2 if rule_x is not None else None
    box = _row_crop_box(
        row,
        column=args.column,
        page_width=page.width,
        page_height=page.height,
        pad_y=1,
        left_override=content_left,
    )
    crop = page.crop(box).convert("L")
    models = load_facit(args.facit)
    result = analyse_row_exact(crop, models, threshold=args.threshold)
    if result["baseline"] is None:
        raise SystemExit("could not infer support baseline from existing exact glyphs")

    covered = set().union(*(match.pixels for match in result["selected"])) if result["selected"] else set()
    residual = result["ink"] - covered
    components = residual_component_pixels(residual)

    payload = json.loads(args.facit.read_text(encoding="utf-8"))
    source = {
        "page": args.page,
        "column": args.column,
        "row": args.row,
        "residual_components": [],
        "source": source_url,
    }
    counts = {"added": 0, "merged": 0}
    for label, indices in args.glyph:
        glyph_source = dict(source)
        glyph_source["residual_components"] = [f"U{index:02d}" for index in indices]
        glyph = glyph_from_components(
            label,
            args.style,
            components,
            indices,
            int(result["baseline"]),
            glyph_source,
        )
        outcome = add_or_merge_glyph(payload, glyph)
        counts[outcome] += 1
        print(f"{outcome}: label={label!r} style={args.style} components={','.join(glyph_source['residual_components'])}")

    if counts["added"] or counts["merged"]:
        args.facit.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"facit={args.facit} residual_components={len(components)} "
        f"added={counts['added']} merged={counts['merged']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())