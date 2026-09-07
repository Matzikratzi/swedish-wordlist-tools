from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path
from typing import Iterable

from .ocr_glyph_matcher import GlyphModel, load_facit


LeftEdgeSignature = tuple[int | None, ...]


def left_edge_signature(model: GlyphModel) -> LeftEdgeSignature:
    """Return the glyph's normalized left contour, one value per raster row.

    The first occupied raster row establishes x=0.  Every following raster row
    contains the x offset of that row's leftmost glyph pixel relative to that
    first leftmost pixel.  Empty raster rows are kept as ``None``; this matters
    for shapes such as a detached dot above a stem.

    The signature is translation invariant in both x and y.  Negative offsets
    are intentional: a glyph may extend farther left below its topmost ink.
    """
    top = model.min_y
    bottom = model.max_y
    first_left = min(x for x, y in model.pixels if y == top)
    by_y: dict[int, int] = {}
    for x, y in model.pixels:
        previous = by_y.get(y)
        if previous is None or x < previous:
            by_y[y] = x
    return tuple(
        None if y not in by_y else by_y[y] - first_left
        for y in range(top, bottom + 1)
    )


def signature_prefix(signature: LeftEdgeSignature, depth: int) -> LeftEdgeSignature:
    """Return a conservative prefix after ``depth`` raster rows.

    No end marker is added for short glyphs.  Thus a completed short glyph stays
    ambiguous with a taller glyph having the same prefix.  That is deliberately
    pessimistic for the proposed live row-start scan, where the next source row
    may contain ink from neighbouring glyphs.
    """
    if depth <= 0:
        raise ValueError("depth must be positive")
    return signature[:depth]


def _groups_for_depth(
    rows: Iterable[tuple[GlyphModel, LeftEdgeSignature]], depth: int
) -> dict[LeftEdgeSignature, list[GlyphModel]]:
    groups: dict[LeftEdgeSignature, list[GlyphModel]] = defaultdict(list)
    for model, signature in rows:
        groups[signature_prefix(signature, depth)].append(model)
    return dict(groups)


def _identity(model: GlyphModel) -> tuple[str, str]:
    return model.label, model.style


def _format_signature(signature: LeftEdgeSignature) -> str:
    return "[" + ",".join("." if value is None else str(value) for value in signature) + "]"


def analyse(models: Iterable[GlyphModel], *, max_depth: int = 24) -> str:
    rows = [(model, left_edge_signature(model)) for model in models if model.pixels]
    if not rows:
        return "left-edge signatures: no glyph models\n"

    lines: list[str] = []
    identities = {_identity(model) for model, _signature in rows}
    max_height = max(len(signature) for _model, signature in rows)
    lines.append(
        "left-edge signatures: "
        f"models={len(rows)} identities={len(identities)} max_height={max_height}"
    )
    lines.append(
        "depth  unique-models  resolved-label/style  mean-candidates  max-candidates  buckets"
    )

    last_depth = min(max_depth, max_height)
    for depth in range(1, last_depth + 1):
        groups = _groups_for_depth(rows, depth)
        unique_models = sum(1 for group in groups.values() if len(group) == 1)
        resolved_models = sum(
            len(group)
            for group in groups.values()
            if len({_identity(model) for model in group}) == 1
        )
        mean_candidates = sum(len(group) * len(group) for group in groups.values()) / len(rows)
        max_candidates = max(len(group) for group in groups.values())
        lines.append(
            f"{depth:>5}  "
            f"{unique_models:>5}/{len(rows):<5} "
            f"({100.0 * unique_models / len(rows):5.1f}%)  "
            f"{resolved_models:>5}/{len(rows):<5} "
            f"({100.0 * resolved_models / len(rows):5.1f}%)  "
            f"{mean_candidates:>15.2f}  "
            f"{max_candidates:>14}  "
            f"{len(groups):>7}"
        )

    full_groups: dict[LeftEdgeSignature, list[GlyphModel]] = defaultdict(list)
    for model, signature in rows:
        full_groups[signature].append(model)
    collisions = [
        (signature, group)
        for signature, group in full_groups.items()
        if len(group) > 1
    ]
    collisions.sort(
        key=lambda item: (
            -len(item[1]),
            _format_signature(item[0]),
            [(_identity(model), model.sources) for model in item[1]],
        )
    )
    unique_full = sum(1 for group in full_groups.values() if len(group) == 1)
    resolved_full = sum(
        len(group)
        for group in full_groups.values()
        if len({_identity(model) for model in group}) == 1
    )
    lines.append("")
    lines.append(
        "full contour: "
        f"unique-models={unique_full}/{len(rows)} "
        f"({100.0 * unique_full / len(rows):.1f}%) "
        f"resolved-label/style={resolved_full}/{len(rows)} "
        f"({100.0 * resolved_full / len(rows):.1f}%) "
        f"collision-buckets={len(collisions)}"
    )

    if collisions:
        lines.append("largest full-contour collisions:")
        for signature, group in collisions[:20]:
            members = ", ".join(
                f"{model.label!r}/{model.style}:px={len(model.pixels)}:sources={model.sources}"
                for model in sorted(
                    group,
                    key=lambda model: (
                        model.label,
                        model.style,
                        -len(model.pixels),
                        -model.sources,
                    ),
                )
            )
            lines.append(
                f"  n={len(group):>2} h={len(signature):>2} "
                f"sig={_format_signature(signature)} -> {members}"
            )

    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Measure how well normalized glyph left-edge contours discriminate "
            "the current SAOL glyph facit."
        )
    )
    parser.add_argument(
        "facit",
        nargs="?",
        default="glyphs/saol14-manual-glyph-facit-v2.json",
        help="manual glyph facit JSON (default: %(default)s)",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=24,
        help="maximum number of raster rows to report (default: %(default)s)",
    )
    args = parser.parse_args()
    if args.max_depth <= 0:
        parser.error("--max-depth must be positive")
    models = load_facit(Path(args.facit))
    print(analyse(models, max_depth=args.max_depth), end="")


if __name__ == "__main__":
    main()
