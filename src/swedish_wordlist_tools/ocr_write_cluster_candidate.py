from __future__ import annotations

import argparse
import json
from pathlib import Path

from .ocr_build_cluster_glyph import (
    _pixels,
    build_cluster_entry,
    find_cluster_placements,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Write one explicitly selected candidate from ocr_build_cluster_glyph."
    )
    parser.add_argument("facit", type=Path)
    parser.add_argument("--candidate", type=int, required=True)
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
    if not left_entries or not right_entries:
        raise SystemExit("hittade inte begärda komponentglyphar")

    placements = find_cluster_placements(
        left_entries,
        right_entries,
        contacts=args.contacts,
        min_dx=args.min_dx,
        max_dx=args.max_dx,
    )
    if args.candidate < 0 or args.candidate >= len(placements):
        raise SystemExit(
            f"candidate {args.candidate} finns inte; giltigt intervall är 0..{len(placements) - 1}"
        )

    placement = placements[args.candidate]
    cluster = build_cluster_entry(args.label, placement, glyphs)
    normalized = frozenset(tuple(p) for p in cluster["pixels_relative_to_baseline"])

    for existing in glyphs:
        if existing.get("label") == args.label and _pixels(existing) == normalized:
            raise SystemExit(
                f"identisk {args.label!r}-glyph finns redan: {existing.get('model_id')}"
            )

    print(
        f"cluster-write: candidate={args.candidate} "
        f"{placement.left_model_id}+{placement.right_model_id} "
        f"dx={placement.dx} contacts={placement.contacts} "
        f"pixels={len(normalized)} holes={len(placement.enclosed_white)} "
        f"-> {cluster['model_id']} label={args.label!r}"
    )

    if not args.write:
        print("cluster-write: dry-run; använd --write för att lägga till glyphen")
        return

    glyphs.append(cluster)
    args.facit.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"cluster-write: skrev {cluster['model_id']} till {args.facit}")


if __name__ == "__main__":
    main()
