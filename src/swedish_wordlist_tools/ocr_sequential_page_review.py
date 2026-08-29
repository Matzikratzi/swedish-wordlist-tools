from __future__ import annotations

import argparse
import json
import urllib.request
from collections import Counter
from pathlib import Path
from tempfile import NamedTemporaryFile

from PIL import Image

from . import ocr_exact_glyph_review_queue_v12 as review_v12
from . import ocr_prepare_sequential_page as sequential_page
from .ocr_editable_unknown_glyph_review import build_html as build_editable_unknown_html
from .ocr_glyph_facit_table import build_html as build_facit_html
from .ocr_glyph_matcher import load_facit
from .ocr_unique_unknown_glyph_review import collect_candidates


def _safe_load_source_image(source: str) -> Image.Image | None:
    """Load a local page image or URL without treating an empty path as '.'."""
    if not source:
        return None
    local = Path(source)
    if local.is_file():
        return Image.open(local).convert("L")
    try:
        with urllib.request.urlopen(source, timeout=30) as response, NamedTemporaryFile(suffix=".png") as tmp:
            tmp.write(response.read())
            tmp.flush()
            return Image.open(tmp.name).convert("L")
    except Exception:
        return None


def _analyse_with_debug_metadata(path: Path, models):
    row = review_v12._analyse_one(path, models)
    debug = json.loads(path.read_text(encoding="utf-8"))
    row["jsonl_hint"] = debug.get("jsonl_hint")
    row["page_word_bbox"] = debug.get("page_word_bbox")
    row["page_source"] = debug.get("page_source")
    return row


def _is_jsonl_anchored(row: dict) -> bool:
    """Return true only for OCR boxes aligned to dictionary text in JSONL."""
    hint = row.get("jsonl_hint")
    return isinstance(hint, dict) and bool(str(hint.get("text") or "").strip())


def _ordered_exact(row: dict) -> list[dict]:
    return sorted(
        [m for m in row.get("exact") or [] if str(m.get("label") or "")],
        key=lambda m: (int(m.get("x") or 0), str(m.get("label") or "")),
    )


def _style_runs(row: dict) -> list[dict]:
    """Collapse exact glyphs into adjacent typography runs.

    This is deliberately descriptive, not normative. Mixed styles in one OCR
    box are normal in SAOL (headword, POS marker, inflection, explanation). We
    therefore record what the exact raster matches show instead of treating
    style changes as errors.
    """
    runs: list[dict] = []
    for match in _ordered_exact(row):
        style = str(match.get("style") or "roman")
        label = str(match.get("label") or "")
        if runs and runs[-1]["style"] == style:
            runs[-1]["text"] += label
            runs[-1]["glyphs"] += 1
        else:
            runs.append({"style": style, "text": label, "glyphs": 1})
    return runs


def _style_sequence(row: dict) -> tuple[str, ...]:
    return tuple(run["style"] for run in _style_runs(row))


def _style_sequence_counts(rows: list[dict]) -> Counter[tuple[str, ...]]:
    counts: Counter[tuple[str, ...]] = Counter()
    for row in rows:
        sequence = _style_sequence(row)
        if sequence:
            counts[sequence] += 1
    return counts


def _style_transition_counts(rows: list[dict]) -> Counter[tuple[str, str]]:
    counts: Counter[tuple[str, str]] = Counter()
    for row in rows:
        sequence = _style_sequence(row)
        for left, right in zip(sequence, sequence[1:]):
            counts[(left, right)] += 1
    return counts


def _row_name(row: dict) -> str:
    hint = row.get("jsonl_hint")
    if isinstance(hint, dict):
        for key in ("ord", "text", "token"):
            value = str(hint.get(key) or "").strip()
            if value:
                return value
    return str(row.get("word") or row.get("expected") or "?")


def _format_style_runs(row: dict) -> str:
    return " | ".join(
        f"{run['style']}:{run['text']}"
        for run in _style_runs(row)
    )


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Read one SAOL facsimile page in sequence, accept exact known glyphs, "
            "and edit only unexplained rasters anchored to JSONL dictionary text."
        )
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--page", type=int, default=1)
    ap.add_argument("--facit", type=Path, default=Path("glyphs/saol14-manual-glyph-facit.json"))
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--review-html", type=Path)
    ap.add_argument("--facit-html", type=Path)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--lang", default="swe")
    ap.add_argument("--psm", type=int, default=4)
    ap.add_argument("--pad-x", type=int, default=1)
    ap.add_argument("--pad-y", type=int, default=5)
    ap.add_argument("--min-confidence", type=float, default=-1.0)
    args = ap.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    review_html = args.review_html or (args.out_dir / "unknown-glyph-review.html")
    facit_html = args.facit_html or (args.out_dir / "glyph-facit-table.html")

    sequential_page._load_source_image = _safe_load_source_image
    report = sequential_page.prepare_page(
        args.jsonl,
        args.page,
        args.out_dir,
        threshold=args.threshold,
        lang=args.lang,
        psm=args.psm,
        pad_x=args.pad_x,
        pad_y=args.pad_y,
        min_confidence=args.min_confidence,
    )

    debug_files = sorted(args.out_dir.glob("saol14-word-debug-*.json"))
    if not debug_files:
        raise SystemExit("page preparation produced no word-debug files")

    models = load_facit(args.facit)
    analysed_all = [_analyse_with_debug_metadata(path, models) for path in debug_files]
    analysed = [row for row in analysed_all if _is_jsonl_anchored(row)]
    excluded_unanchored = len(analysed_all) - len(analysed)

    exact = sum(1 for row in analysed if row.get("fully_exact"))
    incomplete = len(analysed) - exact
    candidates = collect_candidates(analysed)
    occurrences = sum(int(c.get("occurrences") or 0) for c in candidates)
    suggested = sum(1 for c in candidates if c.get("suggestion"))
    five_row_used = sum(1 for row in analysed if row.get("five_row_context_used"))
    sequence_counts = _style_sequence_counts(analysed)
    transition_counts = _style_transition_counts(analysed)
    multi_style_rows = [row for row in analysed if len(_style_sequence(row)) > 1]

    review_html.write_text(build_editable_unknown_html(analysed, args.facit), encoding="utf-8")
    facit_html.write_text(build_facit_html(args.facit), encoding="utf-8")

    print(f"page={args.page}")
    print(f"source={report['source']}")
    print(f"jsonl_rows={report.get('jsonl_rows', 0)}")
    print(f"jsonl_reference_tokens={report.get('jsonl_reference_tokens', 0)}")
    print(f"ocr_words={len(debug_files)}")
    print(f"hinted_words={report.get('hinted_words', 0)}")
    print(f"five_row_context_words={report.get('five_row_context_words', 0)}")
    print(f"five_row_review_words={five_row_used}")
    print(f"review_words={len(analysed)}")
    print(f"excluded_unanchored_words={excluded_unanchored}")
    print(f"fully_exact={exact}")
    print(f"incomplete_words={incomplete}")
    print(f"unknown_occurrences={occurrences}")
    print(f"unique_unknown_rasters={len(candidates)}")
    print(f"candidates_with_jsonl_suggestion={suggested}")
    print(f"multi_style_words={len(multi_style_rows)}")
    print(f"style_sequences={len(sequence_counts)}")
    print(f"style_transitions={sum(transition_counts.values())}")

    if sequence_counts:
        print("\nTYPOGRAPHY SEQUENCES:")
        for sequence, count in sequence_counts.most_common():
            print(f"  {count:4d}  {' -> '.join(sequence)}")

    if transition_counts:
        print("\nTYPOGRAPHY TRANSITIONS:")
        for (left, right), count in transition_counts.most_common():
            print(f"  {count:4d}  {left} -> {right}")

    if multi_style_rows:
        print("\nMULTI-STYLE EXAMPLES:")
        for row in multi_style_rows[:30]:
            print(f"  {_row_name(row)!r}: {_format_style_runs(row)}")

    print(f"review_html={review_html}")
    print(f"facit_html={facit_html}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
