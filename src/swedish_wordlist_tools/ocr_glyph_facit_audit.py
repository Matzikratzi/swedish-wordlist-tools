from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

from .ocr_glyph_matcher import GlyphModel, load_facit


def model_signature(model: GlyphModel) -> tuple[str, str, frozenset[tuple[int, int]]]:
    return model.label, model.style, model.pixels


def exact_mask_duplicate_groups(models: Iterable[GlyphModel]) -> list[list[GlyphModel]]:
    """Return exact pixel masks that have more than one label/style identity."""
    by_mask: dict[frozenset[tuple[int, int]], list[GlyphModel]] = defaultdict(list)
    for model in models:
        by_mask[model.pixels].append(model)

    out: list[list[GlyphModel]] = []
    for rows in by_mask.values():
        identities = {(m.label, m.style) for m in rows}
        if len(identities) > 1:
            out.append(sorted(rows, key=lambda m: (m.label, m.style, -m.sources)))
    return sorted(
        out,
        key=lambda rows: (
            min(m.label for m in rows),
            min(m.style for m in rows),
            len(rows[0].pixels),
        ),
    )


def height_distribution(models: Iterable[GlyphModel]) -> dict[str, Counter[tuple[int, int, int]]]:
    """Count (min_y, max_y, ink-height) tuples per typography class."""
    result: dict[str, Counter[tuple[int, int, int]]] = defaultdict(Counter)
    for model in models:
        result[model.style][(model.min_y, model.max_y, model.max_y - model.min_y + 1)] += 1
    return dict(result)


def format_report(models: Iterable[GlyphModel]) -> str:
    rows = list(models)
    duplicates = exact_mask_duplicate_groups(rows)
    lines = [
        f"FACIT models={len(rows)} exact_mask_duplicate_groups={len(duplicates)}",
        "",
        "EXACT-MASK-DUPLICATES",
    ]
    if not duplicates:
        lines.append("none")
    for index, group in enumerate(duplicates, start=1):
        sample = group[0]
        labels = sorted({m.label for m in group})
        styles = sorted({m.style for m in group})
        lines.append(
            f"GROUP {index} pixels={len(sample.pixels)} width={sample.width} "
            f"y={sample.min_y}..{sample.max_y} height={sample.max_y - sample.min_y + 1} "
            f"labels={labels!r} styles={styles!r}"
        )
        for model in group:
            lines.append(
                f"  MODEL label={model.label!r} style={model.style} sources={model.sources}"
            )

    lines.extend(["", "HEIGHT-DISTRIBUTIONS"])
    distributions = height_distribution(rows)
    for style in sorted(distributions):
        values = distributions[style]
        rendered = ", ".join(
            f"y={min_y}..{max_y}/h={height}:{count}"
            for (min_y, max_y, height), count in sorted(values.items())
        )
        lines.append(f"{style}: {rendered}")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Audit glyph facit for pixel-identical models across labels/styles and "
            "show baseline-relative height distributions. Does not modify facit."
        )
    )
    ap.add_argument(
        "--facit",
        type=Path,
        default=Path("glyphs/saol14-manual-glyph-facit.json"),
    )
    args = ap.parse_args()
    print(format_report(load_facit(args.facit)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
