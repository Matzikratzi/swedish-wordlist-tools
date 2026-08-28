from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

FACIT_FORMAT = "saol14-manual-glyph-facit-v1"


def _shape_key(row: dict[str, Any]) -> tuple[tuple[int, int], ...]:
    pts = [(int(x), int(y)) for x, y in row.get("pixels_relative_to_baseline") or []]
    if not pts:
        return ()
    min_x = min(x for x, _ in pts)
    return tuple(sorted((x - min_x, y) for x, y in pts))


def _render_shape(shape: tuple[tuple[int, int], ...]) -> str:
    if not shape:
        return "(empty raster)"

    xs = [x for x, _ in shape]
    ys = [y for _, y in shape]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    points = set(shape)

    lines = []
    for y in range(min_y, max_y + 1):
        lines.append("".join("#" if (x, y) in points else "." for x in range(min_x, max_x + 1)))
    return "\n".join(lines)


def validate_facit(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("format") != FACIT_FORMAT:
        raise ValueError(f"unsupported facit format: {payload.get('format')!r}")

    glyphs = payload.get("glyphs") or []
    by_shape: dict[tuple[tuple[int, int], ...], list[dict[str, Any]]] = defaultdict(list)
    by_label_style: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)

    for i, row in enumerate(glyphs):
        label = str(row.get("label") or "")
        style = str(row.get("style") or "roman")
        shape = _shape_key(row)
        entry = {
            "index": i,
            "label": label,
            "style": style,
            "pixels": len(shape),
            "sources": len(row.get("sources") or []),
        }
        by_shape[shape].append(entry)
        by_label_style[(label, style)].append(entry)

    exact_duplicates: list[dict[str, Any]] = []
    cross_label_collisions: list[dict[str, Any]] = []
    cross_style_same_label: list[dict[str, Any]] = []

    for shape, rows in by_shape.items():
        if len(rows) < 2:
            continue
        identities = {(r["label"], r["style"]) for r in rows}
        labels = {r["label"] for r in rows}
        styles = {r["style"] for r in rows}
        collision = {
            "pixels": len(shape),
            "raster": _render_shape(shape),
            "models": rows,
        }
        if len(identities) == 1:
            exact_duplicates.append(collision)
        elif len(labels) > 1:
            cross_label_collisions.append(collision)
        elif len(styles) > 1:
            cross_style_same_label.append(collision)

    variants = [
        {
            "label": label,
            "style": style,
            "variants": len(rows),
        }
        for (label, style), rows in sorted(by_label_style.items())
        if len(rows) > 1
    ]

    return {
        "format": "saol14-glyph-facit-validation-v1",
        "facit": str(path),
        "models": len(glyphs),
        "unique_shapes": len(by_shape),
        "label_style_pairs": len(by_label_style),
        "variant_groups": variants,
        "exact_duplicate_groups": exact_duplicates,
        "cross_label_collisions": cross_label_collisions,
        "cross_style_same_label_shapes": cross_style_same_label,
    }


def _print_collision_group(title: str, groups: list[dict[str, Any]]) -> None:
    if not groups:
        return

    print(f"\n{title}:")
    for i, group in enumerate(groups, 1):
        print(f"\n[{i}] {group['pixels']} px")
        for model in group["models"]:
            print(
                f"  index={model['index']} "
                f"label={model['label']!r} "
                f"style={model['style']} "
                f"sources={model['sources']}"
            )
        print("  raster:")
        for line in str(group["raster"]).splitlines():
            print(f"    {line}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate SAOL glyph facit for duplicate and ambiguous exact raster shapes.")
    ap.add_argument("facit", type=Path)
    ap.add_argument("--json-out", type=Path)
    args = ap.parse_args()

    result = validate_facit(args.facit)
    print(f"models={result['models']} unique_shapes={result['unique_shapes']} label_style_pairs={result['label_style_pairs']}")
    print(f"variant_groups={len(result['variant_groups'])}")
    print(f"exact_duplicate_groups={len(result['exact_duplicate_groups'])}")
    print(f"cross_label_collisions={len(result['cross_label_collisions'])}")
    print(f"cross_style_same_label_shapes={len(result['cross_style_same_label_shapes'])}")

    _print_collision_group("AMBIGUOUS EXACT SHAPES", result["cross_label_collisions"])
    _print_collision_group("SAME RASTER, DIFFERENT STYLES (ERROR)", result["cross_style_same_label_shapes"])
    _print_collision_group("REDUNDANT DUPLICATES", result["exact_duplicate_groups"])

    if args.json_out:
        args.json_out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"json={args.json_out}")

    has_error = bool(result["cross_label_collisions"] or result["cross_style_same_label_shapes"])
    return 1 if has_error else 0


if __name__ == "__main__":
    raise SystemExit(main())
