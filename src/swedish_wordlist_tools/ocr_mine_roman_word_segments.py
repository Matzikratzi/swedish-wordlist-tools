from __future__ import annotations

import argparse
import json
import tempfile
from collections import Counter
from pathlib import Path

from PIL import Image

from .ocr_mine_jsonl_pages import _crop_columns, _download, _ocr_tsv, _parse_pages, _source_for_page
from .ocr_mine_typographic_text_templates import (
    _article_words,
    _load_page_entries,
    _ordered_token_alignment,
    _token_specs,
)
from .ocr_match_jsonl import rank_articles
from .ocr_saol_normalize import normalize_text_for_match
from .ocr_tsv_articles import group_articles, read_words
from .ocr_typography_segments import printed_text
from .ocr_word_glyph_read import _segment_word


def _safe_char(ch: str) -> str:
    return ch if ch.isalnum() else f"u{ord(ch):04x}"


def _uniform_style(styles: list[str | None], style: str) -> bool:
    return bool(styles) and all(s == style for s in styles)


def _safe_token(raw: str) -> str:
    return printed_text(normalize_text_for_match(raw).strip()).replace("+", "~")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Mine verified whole roman tokens and resegment them geometrically into glyphs."
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--pages", required=True, help="Page set/range, e.g. 1-30 or 1,4,7")
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--keep-workdir", type=Path)
    ap.add_argument("--limit-words", type=int, default=5000)
    ap.add_argument("--min-headword-score", type=float, default=0.72)
    ap.add_argument(
        "--tokens",
        nargs="*",
        default=None,
        help="Optional exact roman tokens to keep, e.g. pl. best. el.; omit for all uniform-roman tokens.",
    )
    args = ap.parse_args()

    pages = _parse_pages(args.pages)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    glyph_dir = args.out_dir / "roman"
    word_dir = args.out_dir / "words"
    glyph_dir.mkdir(parents=True, exist_ok=True)
    word_dir.mkdir(parents=True, exist_ok=True)

    wanted = None
    if args.tokens:
        wanted = {_safe_token(x) for x in args.tokens}

    owned = None
    if args.keep_workdir:
        workroot = args.keep_workdir
        workroot.mkdir(parents=True, exist_ok=True)
    else:
        owned = tempfile.TemporaryDirectory(prefix="saol-roman-word-pages-")
        workroot = Path(owned.name)

    rows: list[dict[str, object]] = []
    counts: Counter[str] = Counter()
    stats: Counter[str] = Counter()
    physical_seen: set[tuple[object, ...]] = set()

    stop = False
    for page in pages:
        if stop:
            break
        source = _source_for_page(args.jsonl, page)
        if not source:
            stats["missing-source"] += 1
            continue
        page_dir = workroot / f"page-{page:05d}"
        page_dir.mkdir(parents=True, exist_ok=True)
        image_path = page_dir / Path(source).name
        if not image_path.exists():
            _download(source, image_path)
        columns = _crop_columns(image_path, page_dir)

        entries = _load_page_entries(args.jsonl, page)
        for colno, (column_path, column_left) in enumerate(columns, 1):
            if stop:
                break
            tsv = page_dir / f"column-{colno}.tsv"
            _ocr_tsv(column_path, tsv)
            with tsv.open("r", encoding="utf-8", newline="") as f:
                articles = group_articles(read_words(f))
            column_img = Image.open(column_path).convert("L")

            for entry in entries:
                if len(rows) >= args.limit_words:
                    stop = True
                    break
                text = entry.get("text")
                if not isinstance(text, str) or not text:
                    continue
                ranked = [
                    r for r in rank_articles(entry, articles)
                    if r.headword_score >= args.min_headword_score
                ]
                if not ranked:
                    continue
                best = ranked[0]
                article = next((a for a in articles if a.paragraph == best.paragraph), None)
                if article is None:
                    continue

                for (raw, styles), word, score in _ordered_token_alignment(
                    _token_specs(text), _article_words(article)
                ):
                    if len(rows) >= args.limit_words:
                        stop = True
                        break
                    if score != 1.0 or not _uniform_style(styles, "roman"):
                        continue
                    expected = _safe_token(raw)
                    observed = normalize_text_for_match(word.text).strip().replace("+", "~")
                    if not expected or expected != observed or len(expected) != len(styles):
                        continue
                    if wanted is not None and expected not in wanted:
                        continue
                    if word.height < 6 or word.height > 18 or word.width < 2:
                        stats["rejected-word-geometry"] += 1
                        continue

                    physical = (page, colno, entry.get("subnr"), word.left, word.top, word.width, word.height, expected)
                    if physical in physical_seen:
                        stats["duplicate-word"] += 1
                        continue
                    physical_seen.add(physical)

                    crop = column_img.crop(
                        (word.left, word.top, word.left + word.width, word.top + word.height)
                    )
                    segments = _segment_word(crop, len(expected))
                    if len(segments) != len(expected):
                        stats["segment-count"] += 1
                        continue

                    source_id = len(rows)
                    safe_token = "".join(c if c.isalnum() else f"u{ord(c):04x}" for c in expected)
                    word_file = word_dir / f"w{source_id:05d}-sub{entry.get('subnr')}-p{page}-c{colno}-{safe_token}.png"
                    crop.save(word_file)
                    glyphs = []
                    for i, ((_x0, _x1, glyph), ch) in enumerate(zip(segments, expected)):
                        label = _safe_char(ch)
                        n = counts[ch]
                        glyph_file = glyph_dir / f"{label}-{n:05d}-src{source_id:05d}-sub{entry.get('subnr')}-p{page}-c{colno}-i{i}.png"
                        glyph.save(glyph_file)
                        counts[ch] += 1
                        glyphs.append({
                            "character": ch,
                            "index": i,
                            "file": str(glyph_file.relative_to(args.out_dir)),
                        })

                    rows.append({
                        "source_id": source_id,
                        "page": page,
                        "column": colno,
                        "column_left": column_left,
                        "subnr": entry.get("subnr"),
                        "paragraph": article.paragraph,
                        "expected_word": expected,
                        "ocr_word": word.text,
                        "word_bbox": [word.left, word.top, word.width, word.height],
                        "word_file": str(word_file.relative_to(args.out_dir)),
                        "glyphs": glyphs,
                    })
                    stats["words"] += 1
                    stats["glyphs"] += len(glyphs)

    independent_by_class: dict[str, int] = {}
    for ch in counts:
        independent_by_class[ch] = len({
            (row["page"], row["subnr"], row["source_id"])
            for row in rows
            if any(g["character"] == ch for g in row["glyphs"])
        })

    payload = {
        "pages": pages,
        "style": "roman",
        "word_count": len(rows),
        "glyph_count": sum(counts.values()),
        "counts": dict(sorted(counts.items())),
        "independent_sources_by_class": dict(sorted(independent_by_class.items())),
        "stats": dict(sorted(stats.items())),
        "words": rows,
        "notes": {
            "identity": "exact JSONL/OCR token agreement",
            "style": "only tokens whose entire typography mask is roman",
            "segmentation": "whole-word geometric _segment_word; no Tesseract character labels",
            "square_brackets": "excluded by typography classifier",
        },
    }
    manifest = args.out_dir / "manifest-word-segments.json"
    manifest.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    json.dump(payload, __import__("sys").stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
