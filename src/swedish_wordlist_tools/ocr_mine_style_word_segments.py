from __future__ import annotations

import argparse
import json
import tempfile
from collections import Counter
from pathlib import Path

from PIL import Image

from .ocr_mine_jsonl_pages import _crop_columns, _download, _ocr_tsv, _parse_pages, _source_for_page
from .ocr_mine_typographic_text_templates import _article_words, _load_page_entries, _ordered_token_alignment, _token_specs
from .ocr_match_jsonl import rank_articles
from .ocr_saol_normalize import normalize_text_for_match
from .ocr_tsv_articles import group_articles, read_words
from .ocr_typography_segments import printed_text
from .ocr_word_glyph_read import _segment_word


def _safe_char(ch: str) -> str:
    return ch if ch.isalnum() else f"u{ord(ch):04x}"


def _safe_token(raw: str) -> str:
    return printed_text(normalize_text_for_match(raw).strip())


def _uniform_style(styles: list[str | None]) -> str | None:
    if not styles:
        return None
    concrete = {s for s in styles if s is not None}
    if len(concrete) != 1 or any(s is None for s in styles):
        return None
    style = next(iter(concrete))
    return style if style in {"roman", "italic"} else None


def _assign_character_spans(
    segments: list[tuple[int, int, Image.Image]], expected: str
) -> list[tuple[int, int]] | None:
    """Assign one or more consecutive expected characters to each segment.

    The topology segmenter may deliberately stop with fewer image components than
    expected characters when two printed letters really touch. We then need only
    decide *which* component is the multi-letter cluster so that the surrounding
    one-character components can still be used as trusted glyphs.

    A tiny dynamic program partitions the expected character count among the
    observed components. Width per assigned character is compared with the word's
    average width; multi-character assignments carry a small penalty so isolated
    glyphs are preferred whenever geometry supports them.
    """
    m = len(segments)
    n = len(expected)
    if not segments or m > n:
        return None
    if m == n:
        return [(i, i + 1) for i in range(n)]

    widths = [max(1, seg[2].width) for seg in segments]
    unit = max(1.0, sum(widths) / float(n))
    inf = 1e18
    dp: list[dict[int, tuple[float, list[tuple[int, int]]]]] = [dict() for _ in range(m + 1)]
    dp[0][0] = (0.0, [])

    for i in range(m):
        remaining_segments = m - i - 1
        for consumed, (base_cost, spans) in dp[i].items():
            max_k = n - consumed - remaining_segments
            for k in range(1, max_k + 1):
                end = consumed + k
                observed_per_char = widths[i] / float(k)
                width_cost = ((observed_per_char - unit) / unit) ** 2
                cluster_penalty = 0.12 * (k - 1)
                cost = base_cost + width_cost + cluster_penalty
                old = dp[i + 1].get(end)
                candidate = (cost, spans + [(consumed, end)])
                if old is None or cost < old[0]:
                    dp[i + 1][end] = candidate

    result = dp[m].get(n)
    return result[1] if result is not None else None


def main() -> int:
    ap = argparse.ArgumentParser(description="Mine verified whole roman/italic tokens and geometrically segment them into glyphs.")
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--pages", required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--keep-workdir", type=Path)
    ap.add_argument("--styles", default="roman,italic", help="Comma-separated styles")
    ap.add_argument("--limit-words", type=int, default=5000)
    ap.add_argument("--min-headword-score", type=float, default=0.72)
    args = ap.parse_args()

    wanted_styles = {s.strip() for s in args.styles.split(",") if s.strip()}
    if not wanted_styles or not wanted_styles <= {"roman", "italic"}:
        raise SystemExit("--styles must contain roman and/or italic")

    pages = _parse_pages(args.pages)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    word_dir = args.out_dir / "words"
    cluster_dir = args.out_dir / "clusters"
    word_dir.mkdir(parents=True, exist_ok=True)
    cluster_dir.mkdir(parents=True, exist_ok=True)
    for style in wanted_styles:
        (args.out_dir / style).mkdir(parents=True, exist_ok=True)

    if args.keep_workdir:
        workroot = args.keep_workdir
        workroot.mkdir(parents=True, exist_ok=True)
        owned = None
    else:
        owned = tempfile.TemporaryDirectory(prefix="saol-style-word-pages-")
        workroot = Path(owned.name)

    rows: list[dict[str, object]] = []
    counts: dict[str, Counter[str]] = {s: Counter() for s in wanted_styles}
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
                ranked = [r for r in rank_articles(entry, articles) if r.headword_score >= args.min_headword_score]
                if not ranked:
                    continue
                best = ranked[0]
                article = next((a for a in articles if a.paragraph == best.paragraph), None)
                if article is None:
                    continue

                for (raw, styles), word, score in _ordered_token_alignment(_token_specs(text), _article_words(article)):
                    if len(rows) >= args.limit_words:
                        stop = True
                        break
                    if score != 1.0:
                        continue
                    style = _uniform_style(styles)
                    if style not in wanted_styles:
                        continue
                    expected = _safe_token(raw)
                    observed = normalize_text_for_match(word.text).strip()
                    if not expected or expected != observed or len(expected) != len(styles):
                        continue
                    if word.height < 6 or word.height > 18 or word.width < 2:
                        stats["rejected-word-geometry"] += 1
                        continue

                    physical = (page, colno, entry.get("subnr"), word.left, word.top, word.width, word.height, expected, style)
                    if physical in physical_seen:
                        stats["duplicate-word"] += 1
                        continue
                    physical_seen.add(physical)

                    crop = column_img.crop((word.left, word.top, word.left + word.width, word.top + word.height))
                    segments = _segment_word(crop, len(expected), style=style, expected_text=expected)
                    spans = _assign_character_spans(segments, expected)
                    if spans is None:
                        stats["segment-assignment"] += 1
                        continue

                    source_id = len(rows)
                    safe_token = "".join(c if c.isalnum() else f"u{ord(c):04x}" for c in expected)
                    word_file = word_dir / f"w{source_id:05d}-{style}-sub{entry.get('subnr')}-p{page}-c{colno}-{safe_token}.png"
                    crop.save(word_file)

                    glyphs: list[dict[str, object]] = []
                    segment_rows: list[dict[str, object]] = []
                    cluster_count = 0
                    cluster_chars = 0
                    for i, ((x0, x1, glyph), (start, end)) in enumerate(zip(segments, spans)):
                        text_span = expected[start:end]
                        if end - start == 1:
                            ch = text_span
                            label = _safe_char(ch)
                            n = counts[style][ch]
                            glyph_file = args.out_dir / style / f"{label}-{n:05d}-src{source_id:05d}-sub{entry.get('subnr')}-p{page}-c{colno}-i{i}.png"
                            glyph.save(glyph_file)
                            counts[style][ch] += 1
                            rel = str(glyph_file.relative_to(args.out_dir))
                            item = {
                                "kind": "glyph", "character": ch, "expected_text": ch,
                                "index": i, "char_start": start, "char_end": end,
                                "x": [x0, x1], "file": rel,
                            }
                            glyphs.append({"character": ch, "index": i, "file": rel})
                            segment_rows.append(item)
                        else:
                            cluster_count += 1
                            cluster_chars += end - start
                            cluster_file = cluster_dir / f"cluster-src{source_id:05d}-sub{entry.get('subnr')}-p{page}-c{colno}-i{i}-{start}-{end}.png"
                            glyph.save(cluster_file)
                            segment_rows.append({
                                "kind": "cluster", "expected_text": text_span, "index": i,
                                "char_start": start, "char_end": end, "x": [x0, x1],
                                "file": str(cluster_file.relative_to(args.out_dir)),
                                "usable": False,
                            })

                    rows.append({
                        "source_id": source_id, "style": style, "page": page, "column": colno,
                        "column_left": column_left, "subnr": entry.get("subnr"), "paragraph": article.paragraph,
                        "expected_word": expected, "ocr_word": word.text,
                        "word_bbox": [word.left, word.top, word.width, word.height],
                        "word_file": str(word_file.relative_to(args.out_dir)),
                        "glyphs": glyphs, "segments": segment_rows,
                        "cluster_count": cluster_count, "cluster_character_count": cluster_chars,
                    })
                    stats["words"] += 1
                    stats[f"words-{style}"] += 1
                    stats["glyphs"] += len(glyphs)
                    stats[f"glyphs-{style}"] += len(glyphs)
                    if cluster_count:
                        stats["words-with-clusters"] += 1
                        stats["clusters"] += cluster_count
                        stats["cluster-characters"] += cluster_chars
                        stats["salvaged-glyphs-around-clusters"] += len(glyphs)

    independent: dict[str, dict[str, int]] = {s: {} for s in wanted_styles}
    for style in wanted_styles:
        for ch in counts[style]:
            independent[style][ch] = len({
                row["source_id"] for row in rows
                if row["style"] == style and any(g["character"] == ch for g in row["glyphs"])
            })

    payload = {
        "pages": pages,
        "styles": sorted(wanted_styles),
        "word_count": len(rows),
        "glyph_count": sum(sum(c.values()) for c in counts.values()),
        "counts": {s: dict(sorted(counts[s].items())) for s in sorted(wanted_styles)},
        "independent_sources_by_class": {s: dict(sorted(independent[s].items())) for s in sorted(wanted_styles)},
        "stats": dict(sorted(stats.items())),
        "words": rows,
        "notes": {
            "identity": "exact JSONL/OCR token agreement",
            "style": "only tokens whose complete typography mask has one style",
            "segmentation": "x gaps plus strict zero-width topological seams that cannot cut 8-connected ink",
            "clusters": "unsplittable multi-character ink components are excluded; surrounding single-character glyphs are retained",
            "square_brackets": "excluded by typography classifier",
        },
    }
    (args.out_dir / "manifest-style-word-segments.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    json.dump(payload, __import__("sys").stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
