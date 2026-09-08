from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

from .ocr_glyph_matcher import GlyphModel, load_facit
from .ocr_left_edge_local_index import LocalSignature, local_relation_windows


def _identity(model: GlyphModel) -> tuple[str, str]:
    return model.label, model.style


def analyse(models: list[GlyphModel], *, max_steps: int, max_row_gap: int) -> str:
    lines = [
        f"local-left-edge: models={len(models)} max_row_gap={max_row_gap}",
        "steps windows buckets mean-candidates median-candidates p95-candidates max-candidates unique-windows resolved-windows",
    ]

    for steps in range(1, max_steps + 1):
        buckets: dict[LocalSignature, list] = defaultdict(list)
        windows = []
        for model in models:
            for indexed in local_relation_windows(model, steps=steps, max_row_gap=max_row_gap):
                windows.append(indexed)
                buckets[indexed.signature].append(indexed)

        if not windows:
            lines.append(f"{steps:>5} 0 0 - - - - 0/0 0/0")
            continue

        sizes = sorted(len(buckets[item.signature]) for item in windows)
        n = len(sizes)
        median = sizes[n // 2]
        p95 = sizes[min(n - 1, int(0.95 * (n - 1)))]
        mean = sum(sizes) / n
        max_candidates = max(sizes)
        unique = sum(1 for item in windows if len(buckets[item.signature]) == 1)
        resolved = 0
        for item in windows:
            identities = {_identity(candidate.model) for candidate in buckets[item.signature]}
            if len(identities) == 1:
                resolved += 1

        lines.append(
            f"{steps:>5} {len(windows):>7} {len(buckets):>7} {mean:>15.2f} "
            f"{median:>17} {p95:>14} {max_candidates:>14} "
            f"{unique:>6}/{len(windows):<6} {resolved:>6}/{len(windows):<6}"
        )

    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Measure candidate counts for local (dy,dx) left-edge windows that may "
            "start anywhere inside a glyph."
        )
    )
    parser.add_argument(
        "facit",
        nargs="?",
        default="glyphs/saol14-manual-glyph-facit-v2.json",
    )
    parser.add_argument("--max-steps", type=int, default=8)
    parser.add_argument("--max-row-gap", type=int, default=1)
    args = parser.parse_args()
    if args.max_steps <= 0:
        parser.error("--max-steps must be positive")
    if args.max_row_gap <= 0:
        parser.error("--max-row-gap must be positive")
    models = load_facit(Path(args.facit))
    print(analyse(models, max_steps=args.max_steps, max_row_gap=args.max_row_gap), end="")


if __name__ == "__main__":
    main()
