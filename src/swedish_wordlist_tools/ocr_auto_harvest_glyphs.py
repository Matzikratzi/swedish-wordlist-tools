from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from copy import deepcopy
from pathlib import Path
from typing import Any

from . import ocr_exact_glyph_review_queue_v11 as v11
from .ocr_glyph_facit_table import FACIT_FORMAT, build_html as build_facit_html
from .ocr_glyph_matcher import GlyphModel, load_facit, load_word_debug


def _source_key(debug: dict[str, Any], path: Path) -> str:
    page = debug.get("page")
    subnr = debug.get("subnr")
    word = debug.get("expected_word") or debug.get("headword") or ""
    return f"{page}:{subnr}:{word}:{path.name}"


def _half(key: str) -> str:
    """Stable, content-independent discovery/verification split."""
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    return "discover" if digest[0] & 1 == 0 else "verify"


def _expected(debug: dict[str, Any]) -> str:
    return str(debug.get("expected_word") or debug.get("headword") or "")


def _atomic_known_labels(models: list[GlyphModel]) -> set[str]:
    # Multi-character models such as touching ``st`` are useful OCR anchors, but
    # they must not make their individual characters look learned unless those
    # atomic glyphs actually exist in facit.
    return {m.label for m in models if len(m.label) == 1}


def _single_missing_char(expected: str, known: set[str]) -> tuple[int, str] | None:
    missing = [(i, ch) for i, ch in enumerate(expected) if ch not in known]
    if len(missing) != 1:
        return None
    return missing[0]


def _normalize_candidate(points: set[tuple[int, int]], baseline: int) -> list[list[int]]:
    min_x = min(x for x, _ in points)
    return [[x - min_x, y - baseline] for x, y in sorted(points)]


def _candidate_from_debug(path: Path, models: list[GlyphModel], known: set[str]) -> dict[str, Any] | None:
    _ink, _width, _height, debug = load_word_debug(path)
    expected = _expected(debug)
    missing = _single_missing_char(expected, known)
    if missing is None:
        return None
    missing_index, label = missing

    row = v11._analyse_one(path, models)
    baseline = row.get("baseline")
    if baseline is None:
        return None

    exact = sorted(row.get("exact") or [], key=lambda m: (int(m.get("x") or 0), str(m.get("label") or "")))
    recognized = "".join(str(m.get("label") or "") for m in exact)
    expected_without = expected[:missing_index] + expected[missing_index + 1 :]

    # This is the central safety condition: after deleting exactly one unknown
    # transcription character, every remaining character must be explained by
    # exact raster models in the correct left-to-right sequence.
    if recognized != expected_without:
        return None

    unexplained = {tuple(map(int, p)) for p in row.get("unexplained") or []}
    if not unexplained:
        return None

    # No guarded body fragment may survive as an apparently known neighbour.
    # Guarded matches are good evidence that the unknown glyph is composite, but
    # they have already been removed from ``exact`` and therefore remain in the
    # unexplained raster that we harvest as one candidate.
    guarded = row.get("guarded_partial_matches") or []

    style = str(row.get("style") or debug.get("style") or "roman")
    source_key = _source_key(debug, path)
    return {
        "label": label,
        "style": style,
        "pixels_relative_to_baseline": _normalize_candidate(unexplained, int(baseline)),
        "source": {
            "expected_word": expected,
            "page": debug.get("page"),
            "subnr": debug.get("subnr"),
            "source_id": source_key,
            "word_file": str(path),
            "harvest_half": _half(source_key),
            "missing_index": missing_index,
            "guarded_partial_matches": guarded,
        },
    }


def _shape_key(candidate: dict[str, Any]) -> tuple[tuple[int, int], ...]:
    return tuple(sorted((int(x), int(y)) for x, y in candidate["pixels_relative_to_baseline"]))


def harvest(paths: list[Path], facit_path: Path, *, max_labels: int | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    models = load_facit(facit_path)
    known = _atomic_known_labels(models)
    base = json.loads(facit_path.read_text(encoding="utf-8"))
    if base.get("format") != FACIT_FORMAT:
        raise ValueError(f"unsupported facit format: {base.get('format')!r}")

    candidates: list[dict[str, Any]] = []
    rejected = 0
    for path in paths:
        try:
            candidate = _candidate_from_debug(path, models, known)
        except (ValueError, KeyError, json.JSONDecodeError):
            rejected += 1
            continue
        if candidate is not None:
            candidates.append(candidate)

    groups: dict[tuple[str, str], dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for c in candidates:
        groups[(c["label"], c["style"])][c["source"]["harvest_half"]].append(c)

    eligible: list[tuple[tuple[str, str], dict[str, list[dict[str, Any]]]]] = []
    for key, halves in groups.items():
        if halves.get("discover") and halves.get("verify"):
            eligible.append((key, halves))
    eligible.sort(key=lambda item: (-min(len(item[1]["discover"]), len(item[1]["verify"])), item[0][0], item[0][1]))
    if max_labels is not None:
        eligible = eligible[:max_labels]

    provisional = deepcopy(base)
    provisional["policy"] = (
        str(base.get("policy") or "")
        + "; AUTO-HARVESTED CANDIDATES ARE PRELIMINARY: independently isolated in discovery and verification halves; manual approval required"
    ).lstrip("; ")
    provisional["auto_harvest"] = {
        "status": "preliminary",
        "requires_manual_approval": True,
        "split": "sha256(source-key) parity",
    }

    existing = {
        (str(g.get("label") or ""), str(g.get("style") or "roman"), tuple(sorted((int(x), int(y)) for x, y in g.get("pixels_relative_to_baseline") or [])))
        for g in provisional.get("glyphs") or []
    }
    added = 0
    accepted_groups: list[dict[str, Any]] = []
    for (label, style), halves in eligible:
        unique: dict[tuple[tuple[int, int], ...], dict[str, Any]] = {}
        for half in ("discover", "verify"):
            for c in halves[half]:
                shape = _shape_key(c)
                row = unique.setdefault(
                    shape,
                    {
                        "label": label,
                        "style": style,
                        "pixels_relative_to_baseline": [list(p) for p in shape],
                        "sources": [],
                        "provisional": True,
                    },
                )
                row["sources"].append(c["source"])

        group_added = 0
        for shape, row in unique.items():
            key = (label, style, shape)
            if key in existing:
                continue
            provisional.setdefault("glyphs", []).append(row)
            existing.add(key)
            added += 1
            group_added += 1

        accepted_groups.append(
            {
                "label": label,
                "style": style,
                "discover_occurrences": len(halves["discover"]),
                "verify_occurrences": len(halves["verify"]),
                "unique_shapes": len(unique),
                "added_shapes": group_added,
                "discover_words": [c["source"]["expected_word"] for c in halves["discover"]],
                "verify_words": [c["source"]["expected_word"] for c in halves["verify"]],
            }
        )

    report = {
        "debug_files": len(paths),
        "parse_rejected": rejected,
        "known_atomic_labels": sorted(known),
        "isolated_candidates": len(candidates),
        "cross_validated_label_style_groups": len(eligible),
        "provisional_shapes_added": added,
        "groups": accepted_groups,
    }
    return provisional, report


def _collect_inputs(inputs: list[Path]) -> list[Path]:
    out: list[Path] = []
    for path in inputs:
        if path.is_dir():
            out.extend(sorted(path.rglob("*.json")))
        elif path.is_file():
            out.append(path)
    return sorted(dict.fromkeys(out))


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Conservatively auto-harvest unseen glyphs from word-debug JSON, with independent discovery/verification halves."
    )
    ap.add_argument("inputs", nargs="+", type=Path, help="word-debug JSON files or directories")
    ap.add_argument("--facit", type=Path, default=Path("glyphs/saol14-manual-glyph-facit.json"))
    ap.add_argument("--out-facit", type=Path, required=True)
    ap.add_argument("--out-html", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    ap.add_argument("--max-labels", type=int)
    args = ap.parse_args()

    paths = _collect_inputs(args.inputs)
    if not paths:
        raise SystemExit("no word-debug JSON files found")
    provisional, report = harvest(paths, args.facit, max_labels=args.max_labels)
    args.out_facit.write_text(json.dumps(provisional, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.out_html.write_text(build_facit_html(args.out_facit), encoding="utf-8")

    print(f"debug_files={report['debug_files']}")
    print(f"isolated_candidates={report['isolated_candidates']}")
    print(f"cross_validated_groups={report['cross_validated_label_style_groups']}")
    print(f"provisional_shapes_added={report['provisional_shapes_added']}")
    print(f"facit={args.out_facit}")
    print(f"html={args.out_html}")
    print(f"report={args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
