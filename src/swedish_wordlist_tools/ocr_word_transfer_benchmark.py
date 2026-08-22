from __future__ import annotations

import argparse
import json
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image

from .ocr_glyph_consensus_match import classify_consensus, semantic_label
from .ocr_glyph_leave_one_out import _shift_score
from .ocr_tsv_articles import read_words
from .ocr_word_glyph_read import _segment_word


def _raw_best_class(query: Image.Image, refs: list[Path], max_shift: int) -> dict[str, object]:
    best_by_class: dict[str, dict[str, object]] = {}
    for ref in refs:
        score, dx, dy = _shift_score(query, Image.open(ref).convert("L"), max_shift)
        ch = semantic_label(ref)
        row = {
            "character": ch,
            "template": ref.name,
            "score": round(score, 6),
            "dx": dx,
            "dy": dy,
            "reference_count": 1,
        }
        prev = best_by_class.get(ch)
        if prev is None or float(row["score"]) < float(prev["score"]):
            best_by_class[ch] = row
    ranked = sorted(best_by_class.values(), key=lambda r: float(r["score"]))
    best = ranked[0] if ranked else None
    second = ranked[1] if len(ranked) > 1 else None
    margin = None
    if best is not None and second is not None:
        margin = round(float(second["score"]) - float(best["score"]), 6)
    return {"best": best, "second": second, "margin": margin, "ranked": ranked, "query_geometry": None}


def _contains(word, bbox: list[int]) -> bool:
    x, y, w, h = bbox
    cx = x + w / 2
    cy = y + h / 2
    return word.left <= cx <= word.left + word.width and word.top <= cy <= word.top + word.height


def _semantic_text(text: str) -> str:
    return text


def _safe_char(ch: str) -> str:
    return ch if ch.isalnum() else f"u{ord(ch):04x}"


def _locate_word_crop(
    column_image: str,
    column: object,
    source_word: str,
    bbox: list[int],
) -> Image.Image | None:
    img_path = Path(column_image)
    tsv_path = img_path.parent / f"column-{column}.tsv"
    if not img_path.exists() or not tsv_path.exists():
        return None
    with tsv_path.open("r", encoding="utf-8", newline="") as f:
        words = list(read_words(f))
    candidates = [w for w in words if w.text == source_word and _contains(w, bbox)]
    if not candidates:
        candidates = [w for w in words if w.text == source_word]
    if not candidates:
        return None
    word = min(candidates, key=lambda w: abs(w.left - int(bbox[0])))
    return Image.open(img_path).convert("L").crop(
        (word.left, word.top, word.left + word.width, word.top + word.height)
    )


def _build_resegmented_refs(
    groups: dict[tuple[object, ...], list[dict[str, object]]],
    style: str,
    excluded_subnr: object,
    root: Path,
) -> tuple[list[Path], Counter[str]]:
    """Build reference glyphs from whole verified words using test segmentation.

    This intentionally ignores the old per-character PNG crops.  Character
    identity comes from the known expected word; character geometry is produced
    by exactly the same `_segment_word` routine that is later used on the test
    word.  This removes makebox/xclean crop mismatch from the transfer test.
    """
    refs: list[Path] = []
    stats: Counter[str] = Counter()
    physical_seen: set[tuple[object, ...]] = set()
    for key, items in groups.items():
        page, column, subnr, source_word, expected_word, column_image = key
        if subnr == excluded_subnr:
            continue
        if not isinstance(source_word, str) or not isinstance(expected_word, str) or not isinstance(column_image, str):
            stats["missing-metadata"] += 1
            continue
        expected = _semantic_text(expected_word)
        if not expected:
            continue
        bbox = items[0].get("bbox")
        if not isinstance(bbox, list) or len(bbox) != 4:
            stats["missing-bbox"] += 1
            continue
        physical_key = (page, column, subnr, source_word, expected, tuple(bbox))
        if physical_key in physical_seen:
            continue
        physical_seen.add(physical_key)
        crop = _locate_word_crop(column_image, column, source_word, bbox)
        if crop is None:
            stats["word-not-found"] += 1
            continue
        segments = _segment_word(crop, len(expected))
        if len(segments) != len(expected):
            stats["segment-count"] += 1
            continue
        for i, ((_x0, _x1, glyph), ch) in enumerate(zip(segments, expected)):
            out = root / style / f"{_safe_char(ch)}-sub{subnr}-p{page}-c{column}-i{i}.png"
            out.parent.mkdir(parents=True, exist_ok=True)
            glyph.save(out)
            refs.append(out)
            stats["glyphs"] += 1
        stats["words"] += 1
    return refs, stats


def main() -> int:
    ap = argparse.ArgumentParser(description="Cross-word SAOL glyph OCR benchmark using whole word crops and no same-subnr templates.")
    ap.add_argument("library", type=Path)
    ap.add_argument("--style", choices=("italic", "bold", "roman"), required=True)
    ap.add_argument("--max-shift", type=int, default=3)
    ap.add_argument("--margin", type=float, default=0.02)
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--matcher", choices=("consensus", "raw"), default="consensus")
    ap.add_argument("--reference-source", choices=("word-segments", "legacy-glyphs"), default="word-segments")
    ap.add_argument("--diagnostics-out", type=Path, help="Optional directory for word/segment diagnostic PNGs.")
    args = ap.parse_args()

    manifest_path = args.library / "manifest-pages.json"
    if not manifest_path.exists():
        raise SystemExit(f"missing {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    sources = manifest.get("template_sources", {})

    groups: dict[tuple[object, ...], list[dict[str, object]]] = defaultdict(list)
    for output, item in sources.items():
        if item.get("style") != args.style:
            continue
        key = (
            item.get("page"), item.get("column"), item.get("subnr"),
            item.get("source_word"), item.get("expected_word"), item.get("column_image"),
        )
        row = dict(item)
        row["output"] = output
        groups[key].append(row)

    legacy_refs = sorted((args.library / args.style).glob("*.png"))
    results = []
    skipped = Counter()
    char_total = char_correct = word_correct = 0

    if args.diagnostics_out:
        args.diagnostics_out.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="saol-transfer-refs-") as tmp:
        ref_root = Path(tmp)
        for key, items in list(groups.items())[: args.limit]:
            page, column, subnr, source_word, expected_word, column_image = key
            if not isinstance(source_word, str) or not isinstance(expected_word, str) or not isinstance(column_image, str):
                skipped["missing-metadata"] += 1
                continue
            expected = _semantic_text(expected_word)
            if not expected:
                skipped["empty-expected"] += 1
                continue

            bbox = items[0].get("bbox")
            if not isinstance(bbox, list) or len(bbox) != 4:
                skipped["missing-bbox"] += 1
                continue
            crop = _locate_word_crop(column_image, column, source_word, bbox)
            if crop is None:
                skipped["word-not-found"] += 1
                continue

            if args.reference_source == "word-segments":
                refs, ref_stats = _build_resegmented_refs(groups, args.style, subnr, ref_root / f"holdout-{subnr}")
            else:
                needle = f"-sub{subnr}-"
                refs = [p for p in legacy_refs if needle not in p.name]
                ref_stats = Counter({"glyphs": len(refs)})

            ref_classes = {semantic_label(p) for p in refs}
            missing_classes = sorted({ch for ch in expected if ch not in ref_classes})
            if missing_classes:
                skipped["missing-class-after-holdout"] += 1
                continue

            segments = _segment_word(crop, len(expected))
            if len(segments) != len(expected):
                skipped["segment-count"] += 1
                continue

            word_dir = None
            if args.diagnostics_out:
                safe_expected = "".join(_safe_char(ch) for ch in expected)
                word_dir = args.diagnostics_out / f"sub{subnr}-p{page}-c{column}-{safe_expected}"
                word_dir.mkdir(parents=True, exist_ok=True)
                crop.save(word_dir / "word.png")

            pred_chars = []
            margins = []
            segment_rows = []
            accepted = True
            for i, (x0, x1, glyph) in enumerate(segments):
                if args.matcher == "consensus":
                    match = classify_consensus(glyph, refs, max_shift=args.max_shift)
                else:
                    match = _raw_best_class(glyph, refs, args.max_shift)
                best = match["best"]
                second = match["second"]
                margin = match["margin"]
                raw_pred = str(best["character"]) if isinstance(best, dict) else None
                ok_margin = margin is None or float(margin) >= args.margin
                pred = raw_pred if raw_pred is not None and ok_margin else None
                if pred is None:
                    pred_chars.append("?")
                    accepted = False
                else:
                    pred_chars.append(pred)
                margins.append(margin)

                segment_file = None
                if word_dir is not None:
                    segment_file = f"segment-{i:02d}-expected-u{ord(expected[i]):04x}.png"
                    glyph.save(word_dir / segment_file)

                segment_rows.append({
                    "index": i,
                    "expected": expected[i],
                    "x": [x0, x1],
                    "raw_prediction": raw_pred,
                    "prediction": pred,
                    "correct_raw": raw_pred == expected[i],
                    "accepted": pred is not None,
                    "best": best,
                    "second": second,
                    "margin": margin,
                    "query_geometry": match.get("query_geometry"),
                    "segment_file": segment_file,
                })

            pred_text = "".join(pred_chars)
            n_correct = sum(a == b for a, b in zip(pred_text, expected))
            raw_correct = sum(row["correct_raw"] for row in segment_rows)
            char_total += len(expected)
            char_correct += n_correct
            ok = pred_text == expected
            word_correct += int(ok)
            results.append({
                "page": page, "column": column, "subnr": subnr,
                "source_word": source_word, "expected": expected,
                "prediction": pred_text, "correct": ok,
                "accepted_all": accepted,
                "char_correct": n_correct, "char_total": len(expected),
                "raw_char_correct": raw_correct,
                "margins": margins,
                "same_subnr_refs_excluded": True,
                "reference_source": args.reference_source,
                "reference_stats": dict(ref_stats),
                "diagnostic_dir": str(word_dir) if word_dir is not None else None,
                "segments": segment_rows,
            })

    payload = {
        "style": args.style,
        "library": str(args.library),
        "matcher": args.matcher,
        "reference_source": args.reference_source,
        "legacy_template_count": len(legacy_refs),
        "tested_words": len(results),
        "word_correct": word_correct,
        "word_accuracy": round(word_correct / len(results), 4) if results else None,
        "char_correct": char_correct,
        "char_total": char_total,
        "char_accuracy": round(char_correct / char_total, 4) if char_total else None,
        "margin_threshold": args.margin,
        "skipped": dict(sorted(skipped.items())),
        "results": results,
        "notes": {
            "test_unit": "whole OCR-located word crop",
            "character_labels": "not taken from Tesseract",
            "leakage_guard": "all references from test subnr excluded",
            "segmentation": "training and test glyphs use the same whole-word x-ink segmentation",
            "reference_source": "word-segments rebuilds glyphs from verified whole words; legacy-glyphs retained only for A/B comparison",
            "matcher": "weighted aligned per-class median consensus plus mild geometry prior by default",
            "punctuation": "dot remains its own glyph class; plus-like scan artifacts are treated as visual variation",
        },
    }
    json.dump(payload, __import__("sys").stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
