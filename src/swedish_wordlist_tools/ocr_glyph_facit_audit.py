from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

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


def _raw_model_identity(row: dict[str, Any], fmt: str) -> tuple[str, str, frozenset[tuple[int, int]]]:
    style_key = "role" if fmt == "saol14-manual-glyph-facit-v2" else "style"
    style = str(row.get(style_key) or ("unknown" if style_key == "role" else "roman"))
    pixels = frozenset(
        (int(x), int(y)) for x, y in row.get("pixels_relative_to_baseline") or []
    )
    return str(row.get("label") or ""), style, pixels


def load_source_provenance(path: Path) -> dict[tuple[str, str, frozenset[tuple[int, int]]], list[dict[str, Any]]]:
    """Read complete source records without changing the matcher representation."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    fmt = str(payload.get("format") or "")
    out: dict[tuple[str, str, frozenset[tuple[int, int]]], list[dict[str, Any]]] = defaultdict(list)
    for row in payload.get("glyphs") or []:
        identity = _raw_model_identity(row, fmt)
        out[identity].extend(dict(source) for source in row.get("sources") or [])
    return dict(out)


def source_row_location(source: dict[str, Any]) -> tuple[int, int, int] | None:
    """Return page/column/row when a facit source records a physical review row."""
    try:
        if all(key in source for key in ("page", "column", "row")):
            return int(source["page"]), int(source["column"]), int(source["row"])
    except (TypeError, ValueError):
        pass
    return None


def _compact_source(source: dict[str, Any]) -> str:
    preferred = ("page", "column", "row", "expected_word", "source_id", "word_file")
    fields = []
    for key in preferred:
        if key in source:
            fields.append(f"{key}={source[key]!r}")
    for key in sorted(source):
        if key not in preferred:
            fields.append(f"{key}={source[key]!r}")
    return " ".join(fields) if fields else "(tom source-post)"


def format_duplicate_review(
    models: Iterable[GlyphModel],
    provenance: dict[tuple[str, str, frozenset[tuple[int, int]]], list[dict[str, Any]]],
    *,
    jsonl: Path | None = None,
    port: int = 8766,
) -> str:
    """Render source rows for models whose exact mask has conflicting identities."""
    duplicates = exact_mask_duplicate_groups(models)
    lines = ["DUPLICATE-SOURCE-REVIEW"]
    if not duplicates:
        lines.append("none")
        return "\n".join(lines)

    for index, group in enumerate(duplicates, start=1):
        labels = sorted({m.label for m in group})
        styles = sorted({m.style for m in group})
        lines.extend([
            "",
            f"GROUP {index}: SÄRGRANSKA glyph={labels!r} styles={styles!r}",
            "  Samma exakta pixelmask har flera identiteter; avgör klass från tryckkontexten.",
        ])
        for model in group:
            identity = model_signature(model)
            sources = provenance.get(identity) or []
            lines.append(
                f"  MODEL label={model.label!r} style={model.style} sources={len(sources)}"
            )
            if not sources:
                lines.append("    SOURCE saknas i facit")
                continue
            for source_index, source in enumerate(sources, start=1):
                location = source_row_location(source)
                if location is None:
                    lines.append(f"    SOURCE {source_index}: {_compact_source(source)}")
                    lines.append("      ingen page/column/row-position sparad; kan inte öppna femradseditorn direkt")
                    continue
                page, column, row = location
                lines.append(
                    f"    SOURCE {source_index}: page={page} column={column} row={row} "
                    f"-- SÄRGRANSKA {model.label!r} som nu är {model.style}"
                )
                if jsonl is not None:
                    lines.extend([
                        "      PYTHONPATH=src python -m swedish_wordlist_tools.ocr_review_five_rows_glyphs_boundary_html \\",
                        f"        {jsonl} \\",
                        f"        --page {page} --column {column} --row {row} --port {port}",
                    ])
    return "\n".join(lines)


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
    ap.add_argument(
        "--review-duplicates",
        action="store_true",
        help="show source provenance and ordinary five-row-editor commands for exact-mask duplicates",
    )
    ap.add_argument(
        "--jsonl",
        type=Path,
        help="JSONL path inserted into five-row-editor commands printed by --review-duplicates",
    )
    ap.add_argument("--port", type=int, default=8766)
    args = ap.parse_args()

    models = load_facit(args.facit)
    if args.review_duplicates:
        provenance = load_source_provenance(args.facit)
        print(format_duplicate_review(models, provenance, jsonl=args.jsonl, port=args.port))
    else:
        print(format_report(models))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
