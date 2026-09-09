from __future__ import annotations

import argparse
import json
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

Pixel = tuple[int, int]


@dataclass(frozen=True)
class ClusterPlacement:
    left_model_id: str
    right_model_id: str
    dx: int
    contacts: int
    enclosed_white: frozenset[Pixel]
    pixels: frozenset[Pixel]
    left_entry: dict
    right_entry: dict


def _pixels(entry: dict) -> frozenset[Pixel]:
    return frozenset((int(x), int(y)) for x, y in entry["pixels_relative_to_baseline"])


def _shift(pixels: Iterable[Pixel], dx: int) -> frozenset[Pixel]:
    return frozenset((x + dx, y) for x, y in pixels)


def _orthogonal_contacts(left: frozenset[Pixel], right: frozenset[Pixel]) -> int:
    count = 0
    for x, y in left:
        for q in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if q in right:
                count += 1
    return count


def _enclosed_white(pixels: frozenset[Pixel]) -> frozenset[Pixel]:
    if not pixels:
        return frozenset()
    xs = [x for x, _y in pixels]
    ys = [y for _x, y in pixels]
    min_x, max_x = min(xs) - 1, max(xs) + 1
    min_y, max_y = min(ys) - 1, max(ys) + 1

    outside: set[Pixel] = set()
    queue: deque[Pixel] = deque()
    for x in range(min_x, max_x + 1):
        for y in (min_y, max_y):
            if (x, y) not in pixels and (x, y) not in outside:
                outside.add((x, y))
                queue.append((x, y))
    for y in range(min_y, max_y + 1):
        for x in (min_x, max_x):
            if (x, y) not in pixels and (x, y) not in outside:
                outside.add((x, y))
                queue.append((x, y))

    while queue:
        x, y = queue.popleft()
        for qx, qy in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            q = (qx, qy)
            if qx < min_x or qx > max_x or qy < min_y or qy > max_y:
                continue
            if q in pixels or q in outside:
                continue
            outside.add(q)
            queue.append(q)

    enclosed = {
        (x, y)
        for y in range(min_y, max_y + 1)
        for x in range(min_x, max_x + 1)
        if (x, y) not in pixels and (x, y) not in outside
    }
    return frozenset(enclosed)


def find_cluster_placements(
    left_entries: Iterable[dict],
    right_entries: Iterable[dict],
    *,
    contacts: int = 2,
    min_dx: int = 0,
    max_dx: int = 15,
) -> tuple[ClusterPlacement, ...]:
    found: list[ClusterPlacement] = []
    for left_entry in left_entries:
        left = _pixels(left_entry)
        left_holes = len(_enclosed_white(left))
        for right_entry in right_entries:
            right0 = _pixels(right_entry)
            for dx in range(min_dx, max_dx + 1):
                right = _shift(right0, dx)
                if left & right:
                    continue
                contact_count = _orthogonal_contacts(left, right)
                if contact_count != contacts:
                    continue
                union = frozenset(left | right)
                holes = _enclosed_white(union)
                if len(holes) <= left_holes + len(_enclosed_white(right)):
                    continue
                found.append(
                    ClusterPlacement(
                        left_model_id=str(left_entry.get("model_id", "?")),
                        right_model_id=str(right_entry.get("model_id", "?")),
                        dx=dx,
                        contacts=contact_count,
                        enclosed_white=holes,
                        pixels=union,
                        left_entry=left_entry,
                        right_entry=right_entry,
                    )
                )
    return tuple(found)


def _ascii(pixels: frozenset[Pixel], holes: frozenset[Pixel]) -> str:
    xs = [x for x, _y in pixels | holes]
    ys = [y for _x, y in pixels | holes]
    if not xs or not ys:
        return ""
    lines: list[str] = []
    for y in range(min(ys), max(ys) + 1):
        line = ""
        for x in range(min(xs), max(xs) + 1):
            if (x, y) in pixels:
                line += "#"
            elif (x, y) in holes:
                line += "o"
            else:
                line += "."
        lines.append(line)
    return "\n".join(lines)


def _next_model_id(glyphs: Iterable[dict]) -> str:
    highest = 0
    for entry in glyphs:
        model_id = str(entry.get("model_id", ""))
        if model_id.startswith("g") and model_id[1:].isdigit():
            highest = max(highest, int(model_id[1:]))
    return f"g{highest + 1:06d}"


def _normalized_pixels(pixels: frozenset[Pixel]) -> list[list[int]]:
    min_x = min(x for x, _y in pixels)
    return [[x - min_x, y] for x, y in sorted(pixels)]


def _same_optional_value(left: dict, right: dict, key: str) -> str | None:
    a = left.get(key)
    b = right.get(key)
    if a is not None and a == b:
        return str(a)
    return None


def build_cluster_entry(label: str, placement: ClusterPlacement, glyphs: Iterable[dict]) -> dict:
    role = _same_optional_value(placement.left_entry, placement.right_entry, "role")
    entry: dict = {
        "label": label,
        "role": role if role is not None else "unknown",
        "pixels_relative_to_baseline": _normalized_pixels(placement.pixels),
        "sources": [
            {
                "source_id": f"synthetic:{placement.left_model_id}+{placement.right_model_id}",
                "expected_word": label,
                "generated_from": [placement.left_model_id, placement.right_model_id],
                "right_dx": placement.dx,
                "contacts": placement.contacts,
                "enclosed_white_pixels": len(placement.enclosed_white),
                "rule": "same baseline; no overlap; orthogonal contacts; creates enclosed white hole",
            }
        ],
        "reviewed": True,
        "model_id": _next_model_id(glyphs),
    }
    style = _same_optional_value(placement.left_entry, placement.right_entry, "style")
    if style is not None:
        entry["style"] = style
    return entry


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a multi-letter glyph by joining two reviewed glyph rasters on one baseline."
    )
    parser.add_argument("facit", type=Path)
    parser.add_argument("--left-label", default="f")
    parser.add_argument("--right-label", default="r")
    parser.add_argument("--left-pixels", type=int, default=16)
    parser.add_argument("--right-pixels", type=int, default=11)
    parser.add_argument("--label", default="fr")
    parser.add_argument("--contacts", type=int, default=2)
    parser.add_argument("--min-dx", type=int, default=0)
    parser.add_argument("--max-dx", type=int, default=15)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    data = json.loads(args.facit.read_text(encoding="utf-8"))
    glyphs = data.get("glyphs")
    if not isinstance(glyphs, list):
        raise SystemExit("facit saknar glyphs-lista")

    left_entries = [
        entry
        for entry in glyphs
        if entry.get("label") == args.left_label
        and len(_pixels(entry)) == args.left_pixels
        and entry.get("reviewed", False)
    ]
    right_entries = [
        entry
        for entry in glyphs
        if entry.get("label") == args.right_label
        and len(_pixels(entry)) == args.right_pixels
        and entry.get("reviewed", False)
    ]

    print(
        f"cluster-build: left={args.left_label!r}/{args.left_pixels}px models="
        f"{[e.get('model_id') for e in left_entries]}"
    )
    print(
        f"cluster-build: right={args.right_label!r}/{args.right_pixels}px models="
        f"{[e.get('model_id') for e in right_entries]}"
    )
    if not left_entries or not right_entries:
        raise SystemExit("hittade inte begärda komponentglyphar")

    placements = find_cluster_placements(
        left_entries,
        right_entries,
        contacts=args.contacts,
        min_dx=args.min_dx,
        max_dx=args.max_dx,
    )
    print(f"cluster-build: valid_placements={len(placements)}")
    for n, placement in enumerate(placements):
        print(
            f"candidate {n}: {placement.left_model_id}+{placement.right_model_id} "
            f"dx={placement.dx} contacts={placement.contacts} "
            f"pixels={len(placement.pixels)} holes={len(placement.enclosed_white)}"
        )
        print(_ascii(placement.pixels, placement.enclosed_white))

    if len(placements) != 1:
        raise SystemExit("ingen entydig klusterglyph; facit ändras inte")

    placement = placements[0]
    cluster = build_cluster_entry(args.label, placement, glyphs)
    normalized = frozenset(tuple(p) for p in cluster["pixels_relative_to_baseline"])
    for existing in glyphs:
        if existing.get("label") == args.label and _pixels(existing) == normalized:
            raise SystemExit(f"identisk {args.label!r}-glyph finns redan: {existing.get('model_id')}")

    print(
        f"cluster-build: selected={placement.left_model_id}+{placement.right_model_id} "
        f"dx={placement.dx} -> {cluster['model_id']} label={args.label!r} "
        f"pixels={len(normalized)}"
    )
    if not args.write:
        print("cluster-build: dry-run; använd --write för att lägga till glyphen")
        return

    glyphs.append(cluster)
    args.facit.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"cluster-build: skrev {cluster['model_id']} till {args.facit}")


if __name__ == "__main__":
    main()
