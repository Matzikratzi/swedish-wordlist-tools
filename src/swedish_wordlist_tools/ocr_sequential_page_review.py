from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path
from tempfile import NamedTemporaryFile

from PIL import Image

from . import ocr_exact_glyph_review_queue_v11 as review_v11
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
    row = review_v11._analyse_one(path, models)
    debug = json.loads(path.read_text(encoding="utf-8"))
    row["jsonl_hint"] = debug.get("jsonl_hint")
    row["page_word_bbox"] = debug.get("page_word_bbox")
    row["page_source"] = debug.get("page_source")
    return row


def _is_jsonl_anchored(row: dict) -> bool:
    """Return true only for OCR boxes aligned to dictionary text in JSONL."""
    hint = row.get("jsonl_hint")
    return isinstance(hint, dict) and bool(str(hint.get("text") or "").strip())


def _exact_styles(row: dict) -> set[str]:
    """Return the styles of all exact glyph matches in one OCR word.

    SAOL words are assumed to use one typographic style throughout.  Seeing
    multiple exact-match styles in one word therefore indicates a bad facit
    label or another matching error; it is not a legitimate mixed-style word.
    """
    return {
        str(match.get("style") or "roman")
        for match in row.get("exact") or []
        if str(match.get("label") or "")
    }


def _mixed_style_rows(rows: list[dict]) -> list[dict]:
    return [row for row in rows if len(_exact_styles(row)) > 1]


def _row_name(row: dict) -> str:
    hint = row.get("jsonl_hint")
    if isinstance(hint, dict):
        for key in ("ord", "text", "token"):
            value = str(hint.get(key) or "").strip()
            if value:
                return value
    return str(row.get("word") or row.get("expected") or "?")


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
    mixed_style = _mixed_style_rows(analysed)

    review_html.write_text(build_editable_unknown_html(analysed, args.facit), encoding="utf-8")
    facit_html.write_text(build_facit_html(args.facit), encoding="utf-8")

    print(f"page={args.page}")
    print(f"source={report['source']}")
    print(f"jsonl_rows={report.get('jsonl_rows', 0)}")
    print(f"jsonl_reference_tokens={report.get('jsonl_reference_tokens', 0)}")
    print(f"ocr_words={len(debug_files)}")
    print(f"hinted_words={report.get('hinted_words', 0)}")
    print(f"review_words={len(analysed)}")
    print(f"excluded_unanchored_words={excluded_unanchored}")
    print(f"fully_exact={exact}")
    print(f"incomplete_words={incomplete}")
    print(f"unknown_occurrences={occurrences}")
    print(f"unique_unknown_rasters={len(candidates)}")
    print(f"candidates_with_jsonl_suggestion={suggested}")
    print(f"mixed_style_words={len(mixed_style)}")

    if mixed_style:
        print("\nMIXED-STYLE WORDS (ERROR):")
        for row in mixed_style:
            styles = ", ".join(sorted(_exact_styles(row)))
            exact_labels = " ".join(
                f"{match.get('label', '')}{{{str(match.get('style') or 'roman')[0]}}}"
                for match in row.get("exact") or []
            )
            print(f"  {_row_name(row)!r}: styles={styles}; exact={exact_labels}")

    print(f"review_html={review_html}")
    print(f"facit_html={facit_html}")
    return 1 if mixed_style else 0


if __name__ == "__main__":
    raise SystemExit(main())
