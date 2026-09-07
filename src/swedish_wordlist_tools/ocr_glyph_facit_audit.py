from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from .ocr_glyph_matcher import GlyphModel, load_facit


X_HEIGHT_LABELS = frozenset("acegmnopqrsuvwxyz")
ASCENDER_LABELS = frozenset("bdfhijklt")
DIACRITIC_LABELS = frozenset("åäö")
DESCENDER_LABELS = frozenset("gjpqy")

# Size inference is deliberately read-only and typography-oriented.  These
# families keep letters with systematically different top metrics apart; in
# particular i/j and t must not be treated as ordinary ascenders.
SIZE_METRIC_FAMILIES: tuple[tuple[str, frozenset[str]], ...] = (
    ("x-height", X_HEIGHT_LABELS),
    ("ascender", frozenset("bdfhkl")),
    ("i/j", frozenset("ij")),
    ("t", frozenset("t")),
    ("diaeresis", frozenset("äö")),
    ("ring", frozenset("å")),
)


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


def baseline_up_height(model: GlyphModel) -> int:
    """Raster rows from the highest ink pixel down through baseline y=0.

    Pixels below the baseline are deliberately ignored, so e.g. g/j/p/q can
    be compared with ordinary x-height letters without their descenders
    inflating the measurement.
    """
    return max(0, -model.min_y + 1)


def descender_depth(model: GlyphModel) -> int:
    """Raster rows below baseline y=0, reported separately from letter height."""
    return max(0, model.max_y)


def baseline_up_distribution(
    models: Iterable[GlyphModel],
) -> dict[tuple[str, str], Counter[tuple[int, int]]]:
    """Count (baseline-up height, descender depth) separately per label/style."""
    result: dict[tuple[str, str], Counter[tuple[int, int]]] = defaultdict(Counter)
    for model in models:
        result[(model.label, model.style)][
            (baseline_up_height(model), descender_depth(model))
        ] += 1
    return dict(result)


def _metric_group_distribution(
    models: Iterable[GlyphModel], labels: frozenset[str]
) -> dict[str, Counter[int]]:
    result: dict[str, Counter[int]] = defaultdict(Counter)
    for model in models:
        if model.label in labels:
            result[model.style][baseline_up_height(model)] += 1
    return dict(result)


def format_baseline_metric_report(models: Iterable[GlyphModel]) -> str:
    """Render typography-oriented heights measured from the support baseline."""
    rows = list(models)
    distributions = baseline_up_distribution(rows)
    lines = [
        "BASELINE-METRICS",
        "up = raster rows from top ink through support baseline y=0; ink below baseline is ignored",
        "down = raster rows below support baseline, reported separately",
        "",
        "X-HEIGHT-ANCHORS labels=acegmnopqrsuvwxyz",
    ]
    xdist = _metric_group_distribution(rows, X_HEIGHT_LABELS)
    for style in sorted(xdist):
        rendered = ", ".join(f"up={height}:{count}" for height, count in sorted(xdist[style].items()))
        lines.append(f"{style}: {rendered}")

    lines.extend(["", "ASCENDER-TOPS labels=bdfhijklt"])
    adist = _metric_group_distribution(rows, ASCENDER_LABELS)
    for style in sorted(adist):
        rendered = ", ".join(f"up={height}:{count}" for height, count in sorted(adist[style].items()))
        lines.append(f"{style}: {rendered}")

    lines.extend(["", "DIACRITIC-TOPS labels=åäö"])
    ddist = _metric_group_distribution(rows, DIACRITIC_LABELS)
    for style in sorted(ddist):
        rendered = ", ".join(f"up={height}:{count}" for height, count in sorted(ddist[style].items()))
        lines.append(f"{style}: {rendered}")

    lines.extend(["", "PER-LABEL-BASELINE-METRICS"])
    interesting = X_HEIGHT_LABELS | ASCENDER_LABELS | DIACRITIC_LABELS
    for (label, style), values in sorted(distributions.items(), key=lambda item: (item[0][1], item[0][0])):
        if label not in interesting:
            continue
        rendered = ", ".join(
            f"up={up}/down={down}:{count}"
            for (up, down), count in sorted(values.items())
        )
        lines.append(f"{style} {label!r}: {rendered}")
    return "\n".join(lines)


def _dominant_two_modes(values: Counter[int]) -> tuple[int, int] | None:
    """Return the two best-supported distinct heights, ordered small -> large.

    Support count wins; equal support prefers the lower metric.  A family with
    fewer than two observed heights is left unresolved rather than guessed.
    """
    if len(values) < 2:
        return None
    best = sorted(values, key=lambda height: (-values[height], height))[:2]
    return tuple(sorted(best))  # type: ignore[return-value]


def infer_size_metric_modes(
    models: Iterable[GlyphModel],
) -> dict[str, dict[str, tuple[int, int] | None]]:
    """Infer small/large baseline-up modes independently for each style/family."""
    rows = list(models)
    styles = sorted({model.style for model in rows})
    result: dict[str, dict[str, tuple[int, int] | None]] = {}
    for style in styles:
        by_family: dict[str, tuple[int, int] | None] = {}
        style_rows = [model for model in rows if model.style == style]
        for family, labels in SIZE_METRIC_FAMILIES:
            counts = Counter(
                baseline_up_height(model)
                for model in style_rows
                if model.label in labels
            )
            by_family[family] = _dominant_two_modes(counts)
        result[style] = by_family
    return result


def _family_for_label(label: str) -> str | None:
    for family, labels in SIZE_METRIC_FAMILIES:
        if label in labels:
            return family
    return None


def classify_size_models(models: Iterable[GlyphModel]) -> list[dict[str, Any]]:
    """Classify measurable models as small/large/outlier using inferred modes."""
    rows = list(models)
    modes = infer_size_metric_modes(rows)
    out: list[dict[str, Any]] = []
    for model in rows:
        family = _family_for_label(model.label)
        if family is None:
            continue
        pair = modes.get(model.style, {}).get(family)
        up = baseline_up_height(model)
        if pair is None:
            size = "unresolved"
        elif up == pair[0]:
            size = "small"
        elif up == pair[1]:
            size = "large"
        else:
            size = "outlier"
        out.append(
            {
                "label": model.label,
                "style": model.style,
                "family": family,
                "up": up,
                "down": descender_depth(model),
                "size": size,
                "sources": model.sources,
                "mode_pair": pair,
            }
        )
    return sorted(out, key=lambda row: (row["style"], row["family"], row["label"], row["up"], row["down"]))


def format_size_class_report(models: Iterable[GlyphModel]) -> str:
    """Render a read-only audit of the possible two sizes inside each style."""
    rows = list(models)
    modes = infer_size_metric_modes(rows)
    classified = classify_size_models(rows)
    lines = [
        "SIZE-CLASS-INFERENCE (read-only; facit unchanged)",
        "small/large are inferred independently inside each typography metric family",
        "",
        "STYLE-SUMMARY",
    ]
    for style in sorted(modes):
        xpair = modes[style].get("x-height")
        candidate = "yes" if xpair is not None else "not proven"
        rendered_x = "?" if xpair is None else f"{xpair[0]}/{xpair[1]}"
        lines.append(f"{style}: two-size-candidate={candidate} x-height-small/large={rendered_x}")
        for family, _labels in SIZE_METRIC_FAMILIES:
            pair = modes[style].get(family)
            rendered = "unresolved" if pair is None else f"small={pair[0]} large={pair[1]}"
            lines.append(f"  {family}: {rendered}")

    lines.extend(["", "OUTLIERS"])
    outliers = [row for row in classified if row["size"] == "outlier"]
    if not outliers:
        lines.append("none")
    else:
        for row in outliers:
            pair = row["mode_pair"]
            lines.append(
                f"{row['style']} {row['label']!r} family={row['family']} "
                f"up={row['up']} down={row['down']} expected={pair[0]}/{pair[1]} "
                f"sources={row['sources']}"
            )

    lines.extend(["", "UNRESOLVED-FAMILIES"])
    unresolved = [
        (style, family)
        for style, families in modes.items()
        for family, pair in families.items()
        if pair is None
    ]
    if not unresolved:
        lines.append("none")
    else:
        for style, family in unresolved:
            lines.append(f"{style} {family}")

    return "\n".join(lines)


def per_label_height_distribution(
    models: Iterable[GlyphModel],
) -> dict[tuple[str, str], Counter[tuple[int, int, int]]]:
    """Count baseline-relative height tuples separately for each label/style."""
    result: dict[tuple[str, str], Counter[tuple[int, int, int]]] = defaultdict(Counter)
    for model in models:
        key = (model.label, model.style)
        height = model.max_y - model.min_y + 1
        result[key][(model.min_y, model.max_y, height)] += 1
    return dict(result)


def multiple_height_populations(
    models: Iterable[GlyphModel],
) -> dict[tuple[str, str], Counter[tuple[int, int, int]]]:
    """Return label/style identities represented by more than one vertical extent."""
    distributions = per_label_height_distribution(models)
    return {key: values for key, values in distributions.items() if len(values) > 1}


def _format_height_values(values: Counter[tuple[int, int, int]]) -> str:
    return ", ".join(
        f"y={min_y}..{max_y}/h={height}:{count}"
        for (min_y, max_y, height), count in sorted(values.items())
    )


def format_per_label_height_report(models: Iterable[GlyphModel]) -> str:
    """Render all label/style height distributions plus identities with multiple extents."""
    rows = list(models)
    distributions = per_label_height_distribution(rows)
    multiple = multiple_height_populations(rows)
    lines = ["PER-LABEL-HEIGHTS"]
    for (label, style), values in sorted(distributions.items(), key=lambda item: (item[0][1], item[0][0])):
        lines.append(f"{style} {label!r}: {_format_height_values(values)}")

    lines.extend(["", "MULTI-HEIGHT-LABELS"])
    if not multiple:
        lines.append("none")
    else:
        for (label, style), values in sorted(multiple.items(), key=lambda item: (item[0][1], item[0][0])):
            lines.append(f"{style} {label!r}: {_format_height_values(values)}")
    return "\n".join(lines)


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
        lines.append(f"{style}: {_format_height_values(distributions[style])}")
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
        "--per-label-heights",
        action="store_true",
        help="show baseline-relative height populations separately for each label/style",
    )
    ap.add_argument(
        "--baseline-metrics",
        action="store_true",
        help="show baseline-up letter heights with descenders measured separately",
    )
    ap.add_argument(
        "--size-classes",
        action="store_true",
        help="infer read-only small/large typography classes per style and list outliers",
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
    elif args.size_classes:
        print(format_size_class_report(models))
    elif args.baseline_metrics:
        print(format_baseline_metric_report(models))
    elif args.per_label_heights:
        print(format_per_label_height_report(models))
    else:
        print(format_report(models))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
