from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

FACIT_FORMATS = {"saol14-manual-glyph-facit-v1", "saol14-manual-glyph-facit-v2"}


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
    points = set(shape)
    return "\n".join(
        "".join("#" if (x, y) in points else "." for x in range(min(xs), max(xs) + 1))
        for y in range(min(ys), max(ys) + 1)
    )


def validate_facit(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    fmt = payload.get("format")
    if fmt not in FACIT_FORMATS:
        raise ValueError(f"unsupported facit format: {fmt!r}")

    glyphs = payload.get("glyphs") or []
    by_shape: dict[tuple[tuple[int, int], ...], list[dict[str, Any]]] = defaultdict(list)
    by_label_role: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)

    for i, row in enumerate(glyphs):
        label = str(row.get("label") or "")
        role = str(row.get("role") or row.get("style") or "unknown")
        shape = _shape_key(row)
        entry = {
            "index": i,
            "label": label,
            "role": role,
            "pixels": len(shape),
            "sources": len(row.get("sources") or []),
        }
        by_shape[shape].append(entry)
        by_label_role[(label, role)].append(entry)

    exact_duplicates = []
    cross_label_collisions = []
    cross_role_same_label = []
    for shape, rows in by_shape.items():
        if len(rows) < 2:
            continue
        identities = {(r["label"], r["role"]) for r in rows}
        labels = {r["label"] for r in rows}
        roles = {r["role"] for r in rows}
        collision = {"pixels": len(shape), "raster": _render_shape(shape), "models": rows}
        if len(identities) == 1:
            exact_duplicates.append(collision)
        elif len(labels) > 1:
            cross_label_collisions.append(collision)
        elif len(roles) > 1:
            cross_role_same_label.append(collision)

    variants = [
        {"label": label, "role": role, "variants": len(rows)}
        for (label, role), rows in sorted(by_label_role.items())
        if len(rows) > 1
    ]
    return {
        "format": "saol14-glyph-facit-validation-v2",
        "facit": str(path),
        "models": len(glyphs),
        "unique_shapes": len(by_shape),
        "label_role_pairs": len(by_label_role),
        "variant_groups": variants,
        "exact_duplicate_groups": exact_duplicates,
        "cross_label_collisions": cross_label_collisions,
        "cross_role_same_label_shapes": cross_role_same_label,
    }


def _print_collision_group(title: str, groups: list[dict[str, Any]]) -> None:
    if not groups:
        return
    print(f"\n{title}:")
    for i, group in enumerate(groups, 1):
        print(f"\n[{i}] {group['pixels']} px")
        for model in group["models"]:
            print(f"  index={model['index']} label={model['label']!r} role={model['role']} sources={model['sources']}")
        print("  raster:")
        for line in str(group["raster"]).splitlines():
            print(f"    {line}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate SAOL glyph facit for duplicate and ambiguous exact raster shapes.")
    ap.add_argument("facit", type=Path)
    ap.add_argument("--json-out", type=Path)
    args = ap.parse_args()
    result = validate_facit(args.facit)
    print(f"models={result['models']} unique_shapes={result['unique_shapes']} label_role_pairs={result['label_role_pairs']}")
    print(f"variant_groups={len(result['variant_groups'])}")
    print(f"exact_duplicate_groups={len(result['exact_duplicate_groups'])}")
    print(f"cross_label_collisions={len(result['cross_label_collisions'])}")
    print(f"cross_role_same_label_shapes={len(result['cross_role_same_label_shapes'])}")
    _print_collision_group("AMBIGUOUS EXACT SHAPES", result["cross_label_collisions"])
    _print_collision_group("SAME RASTER, DIFFERENT SEMANTIC ROLES (OK)", result["cross_role_same_label_shapes"])
    _print_collision_group("REDUNDANT DUPLICATES", result["exact_duplicate_groups"])
    if args.json_out:
        args.json_out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"json={args.json_out}")
    return 1 if result["cross_label_collisions"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
