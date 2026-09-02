from __future__ import annotations

import argparse
import io
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from time import perf_counter

from .ocr_compare_page_text_prefix import _format_duration
from .ocr_glyph_facit_audit import (
    SIZE_METRIC_FAMILIES,
    baseline_up_height,
    infer_size_metric_modes,
    model_signature,
)
from .ocr_glyph_matcher import load_facit
from .ocr_review_five_rows_glyphs_boundary_html import load_review_state_with_cached_boundaries
from .ocr_review_five_rows_glyphs_fast_html import build_page_context


MAX_INTRA_WORD_GAP = 4


def is_cluster_label(label: str) -> bool:
    """Return True for learned glyph models that encode more than one character.

    The audit deliberately prefers transparency over cleverness: a model with a
    one-character label is a singleton, while every longer label is surfaced as
    a cluster for human review.  No attempt is made to declare clusters safe.
    """
    return len(str(label)) > 1


def cluster_records(state: dict) -> list[dict]:
    out: list[dict] = []
    for match in state.get("matches") or []:
        if not is_cluster_label(match.label):
            continue
        xs = [x for x, _y in match.pixels]
        ys = [y for _x, y in match.pixels]
        out.append(
            {
                "label": match.label,
                "style": match.style,
                "x0": min(xs),
                "x1": max(xs),
                "y0": min(ys),
                "y1": max(ys),
                "pixels": len(match.pixels),
                "sources": int(getattr(match, "sources", 0) or 0),
            }
        )
    return sorted(out, key=lambda item: (item["x0"], item["y0"], item["label"]))


def _family_for_label(label: str) -> str | None:
    for family, labels in SIZE_METRIC_FAMILIES:
        if label in labels:
            return family
    return None


def glyph_size_class_map(models) -> dict[tuple[str, str, frozenset[tuple[int, int]]], str]:
    """Map exact learned model identities to small/large/outlier size classes."""
    rows = list(models)
    modes = infer_size_metric_modes(rows)
    out: dict[tuple[str, str, frozenset[tuple[int, int]]], str] = {}
    for model in rows:
        family = _family_for_label(model.label)
        if family is None:
            continue
        pair = modes.get(model.style, {}).get(family)
        if pair is None:
            size = "unresolved"
        else:
            up = baseline_up_height(model)
            if up == pair[0]:
                size = "small"
            elif up == pair[1]:
                size = "large"
            else:
                size = "outlier"
        out[model_signature(model)] = size
    return out


def _match_signature(match) -> tuple[str, str, frozenset[tuple[int, int]]]:
    pixels = frozenset((x - int(match.x), y - int(match.baseline)) for x, y in match.pixels)
    return str(match.label), str(match.style), pixels


def neighbor_class_warnings(state: dict, class_map: dict) -> list[dict]:
    """Flag a lone style/size class embedded in a locally uniform letter run.

    This is intentionally conservative.  A candidate must be flanked immediately
    by the same class and have at least three supporting neighbours of that class
    inside a five-letter window.  Punctuation/clusters and gaps wider than an
    ordinary inter-letter gap split runs, so typography transitions are not
    treated as evidence by themselves.
    """
    matches = sorted(state.get("matches") or [], key=lambda match: (match.x, match.baseline))
    runs: list[list[dict]] = []
    current: list[dict] = []
    previous_x1: int | None = None

    def flush() -> None:
        nonlocal current, previous_x1
        if current:
            runs.append(current)
        current = []
        previous_x1 = None

    for match in matches:
        label = str(match.label)
        if len(label) != 1 or not label.isalpha():
            flush()
            continue
        size = class_map.get(_match_signature(match))
        if size not in {"small", "large", "outlier"}:
            flush()
            continue
        xs = [x for x, _y in match.pixels]
        x0 = min(xs)
        x1 = max(xs)
        if previous_x1 is not None and x0 - previous_x1 - 1 > MAX_INTRA_WORD_GAP:
            flush()
        current.append(
            {
                "label": label,
                "style": str(match.style),
                "size": size,
                "class": f"{match.style}-{size}",
                "x0": x0,
                "x1": x1,
            }
        )
        previous_x1 = x1
    flush()

    warnings: list[dict] = []
    for run in runs:
        if len(run) < 4:
            continue
        for index in range(1, len(run) - 1):
            candidate = run[index]
            expected = run[index - 1]["class"]
            if run[index + 1]["class"] != expected or candidate["class"] == expected:
                continue
            lo = max(0, index - 2)
            hi = min(len(run), index + 3)
            support = sum(
                1
                for other_index in range(lo, hi)
                if other_index != index and run[other_index]["class"] == expected
            )
            if support < 3:
                continue
            context = "".join(item["label"] for item in run[lo:hi])
            warnings.append(
                {
                    "label": candidate["label"],
                    "x": candidate["x0"],
                    "observed": candidate["class"],
                    "expected": expected,
                    "support": support,
                    "context": context,
                }
            )
    return warnings


def _load_review_state_for_audit(context: dict, position, models) -> dict:
    """Run boundary-aware row analysis quietly until its cuts have settled.

    The interactive loader deliberately returns immediately after learning one
    boundary correction so the browser can refresh.  A batch audit has no such
    refresh, so repeat the same row while it reports a newly learned correction.
    """
    state: dict = {}
    for _attempt in range(8):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            state = load_review_state_with_cached_boundaries(context, position, models)
        if not state.get("row_boundary_correction_learned"):
            return state
    return state


def audit_page(context: dict, models, *, progress=None) -> dict:
    rows: list[dict] = []
    positions = list(context.get("positions") or [])
    class_map = glyph_size_class_map(models)
    for done, position in enumerate(positions, start=1):
        state = _load_review_state_for_audit(context, position, models)
        clusters = cluster_records(state)
        class_warnings = neighbor_class_warnings(state, class_map)
        singleton_count = sum(
            1 for match in state.get("matches") or [] if not is_cluster_label(match.label)
        )
        unknown = max(0, int(state.get("source_pixels") or 0) - int(state.get("covered_pixels") or 0))
        rows.append(
            {
                "column": int(state["column"]),
                "row": int(state["row"]),
                "source_pixels": int(state.get("source_pixels") or 0),
                "covered_pixels": int(state.get("covered_pixels") or 0),
                "unknown_pixels": unknown,
                "fully_exact": unknown == 0,
                "text": str(state.get("text") or ""),
                "singletons": singleton_count,
                "clusters": clusters,
                "class_warnings": class_warnings,
                "boundary_corrections": list(state.get("row_boundary_corrections") or []),
            }
        )
        if progress is not None:
            progress(done, len(positions), position)

    source_pixels = sum(row["source_pixels"] for row in rows)
    covered_pixels = sum(row["covered_pixels"] for row in rows)
    misses = [row for row in rows if row["unknown_pixels"]]
    cluster_rows = [row for row in rows if row["clusters"]]
    warning_rows = [row for row in rows if row["class_warnings"]]
    return {
        "rows": rows,
        "rows_total": len(rows),
        "rows_exact": len(rows) - len(misses),
        "source_pixels": source_pixels,
        "covered_pixels": covered_pixels,
        "unknown_pixels": source_pixels - covered_pixels,
        "misses": misses,
        "cluster_rows": cluster_rows,
        "cluster_matches": sum(len(row["clusters"]) for row in cluster_rows),
        "singleton_matches": sum(row["singletons"] for row in rows),
        "warning_rows": warning_rows,
        "class_warnings": sum(len(row["class_warnings"]) for row in warning_rows),
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Boundary-aware exact glyph audit with explicit review of multi-character glyph clusters."
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--page", type=int, required=True)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--facit", type=Path, default=Path("glyphs/saol14-manual-glyph-facit.json"))
    ap.add_argument(
        "--clusters",
        choices=("summary", "all", "none"),
        default="all",
        help="show all cluster matches (default), only counts, or suppress cluster output",
    )
    args = ap.parse_args()

    context = build_page_context(args.jsonl, args.page, args.threshold)
    models = load_facit(args.facit)
    started = perf_counter()
    last_percent = -1

    def progress(done: int, total: int, position: tuple[int, int]) -> None:
        nonlocal last_percent
        percent = int(100 * done / total) if total else 100
        bucket = percent // 5
        if bucket == last_percent and done not in {1, total}:
            return
        last_percent = bucket
        elapsed = perf_counter() - started
        rate = done / elapsed if elapsed else 0.0
        eta = elapsed * (total - done) / done if done else 0.0
        column, row = position
        print(
            f"page={args.page}: {done}/{total} rader ({percent:3d}%) "
            f"col={column} row={row} elapsed={_format_duration(elapsed)} "
            f"eta={_format_duration(eta)} rate={rate:.2f} rad/s",
            file=sys.stderr,
            flush=True,
        )

    print(
        f"page={args.page}: boundary-aware glyphaudit; residualer kan lära/cacha raka radgränser ...",
        file=sys.stderr,
        flush=True,
    )
    report = audit_page(context, models, progress=progress)
    elapsed = perf_counter() - started
    source = report["source_pixels"]
    pct = 100.0 * report["covered_pixels"] / source if source else 100.0
    print(
        f"page={args.page} rows_exact={report['rows_exact']}/{report['rows_total']} "
        f"glyph_pixels={report['covered_pixels']}/{source} coverage={pct:.2f}% "
        f"unknown_pixels={report['unknown_pixels']} singleton_matches={report['singleton_matches']} "
        f"cluster_matches={report['cluster_matches']} elapsed={_format_duration(elapsed)}"
    )

    if report["misses"]:
        print(f"PIXEL-MISSES {len(report['misses'])}")
        for row in report["misses"]:
            print(
                f"MISS\tcol={row['column']} row={row['row']} "
                f"unknown={row['unknown_pixels']} "
                f"covered={row['covered_pixels']}/{row['source_pixels']} "
                f"text={row['text']!r}"
            )
    else:
        print("PIXEL-MISSES 0")

    if report["class_warnings"]:
        print(f"NEIGHBOR-CLASS-WARNINGS {report['class_warnings']}")
        for row in report["warning_rows"]:
            for warning in row["class_warnings"]:
                print(
                    f"CLASS-WARN\tcol={row['column']} row={row['row']} "
                    f"x={warning['x']} glyph={warning['label']!r} "
                    f"observed={warning['observed']} expected={warning['expected']} "
                    f"support={warning['support']} context={warning['context']!r} "
                    f"text={row['text']!r}"
                )

    if args.clusters != "none":
        print(
            f"CLUSTER-AUDIT rows={len(report['cluster_rows'])} matches={report['cluster_matches']} "
            f"policy='label length > 1; manual review recommended'"
        )
        if args.clusters == "all":
            for row in report["cluster_rows"]:
                print(
                    f"CLUSTER-ROW\tcol={row['column']} row={row['row']} "
                    f"singletons={row['singletons']} clusters={len(row['clusters'])} "
                    f"text={row['text']!r}"
                )
                for item in row["clusters"]:
                    print(
                        f"  CLUSTER label={item['label']!r} style={item['style']} "
                        f"pixels={item['pixels']} x={item['x0']}..{item['x1']} "
                        f"y={item['y0']}..{item['y1']} sources={item['sources']}"
                    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
