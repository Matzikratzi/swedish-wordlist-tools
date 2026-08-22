from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image

from .ocr_glyph_leave_one_out import _label, _shift_score
from .ocr_tsv_articles import read_words
from .ocr_word_glyph_read import _segment_word


def _best_class(query: Image.Image, refs: list[Path], max_shift: int) -> tuple[str | None, float | None, float | None]:
    best_by_class: dict[str, float] = {}
    for ref in refs:
        score, _dx, _dy = _shift_score(query, Image.open(ref).convert("L"), max_shift)
        ch = _label(ref)
        if ch not in best_by_class or score < best_by_class[ch]:
            best_by_class[ch] = score
    ranked = sorted(best_by_class.items(), key=lambda kv: kv[1])
    if not ranked:
        return None, None, None
    best_ch, best_score = ranked[0]
    margin = None if len(ranked) < 2 else ranked[1][1] - best_score
    return best_ch, best_score, margin


def _contains(word, bbox: list[int]) -> bool:
    x, y, w, h = bbox
    cx = x + w / 2
    cy = y + h / 2
    return word.left <= cx <= word.left + word.width and word.top <= cy <= word.top + word.height


def main() -> int:
    ap = argparse.ArgumentParser(description="Cross-word SAOL glyph OCR benchmark using whole word crops and no same-subnr templates.")
    ap.add_argument("library", type=Path)
    ap.add_argument("--style", choices=("italic", "bold", "roman"), required=True)
    ap.add_argument("--max-shift", type=int, default=3)
    ap.add_argument("--margin", type=float, default=0.02)
    ap.add_argument("--limit", type=int, default=50)
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

    all_refs = sorted((args.library / args.style).glob("*.png"))
    results = []
    skipped = Counter()
    char_total = char_correct = word_correct = 0

    for key, items in list(groups.items())[: args.limit]:
        page, column, subnr, source_word, expected_word, column_image = key
        if not isinstance(source_word, str) or not isinstance(expected_word, str) or not isinstance(column_image, str):
            skipped["missing-metadata"] += 1
            continue
        expected = expected_word.replace("+", "~")
        if not expected:
            skipped["empty-expected"] += 1
            continue

        img_path = Path(column_image)
        tsv_path = img_path.parent / f"column-{column}.tsv"
        if not img_path.exists() or not tsv_path.exists():
            skipped["missing-workfile"] += 1
            continue

        # Use one known glyph position merely to disambiguate duplicate OCR words.
        bbox = items[0].get("bbox")
        if not isinstance(bbox, list) or len(bbox) != 4:
            skipped["missing-bbox"] += 1
            continue
        with tsv_path.open("r", encoding="utf-8", newline="") as f:
            words = list(read_words(f))
        candidates = [w for w in words if w.text == source_word and _contains(w, bbox)]
        if not candidates:
            candidates = [w for w in words if w.text == source_word]
        if not candidates:
            skipped["word-not-found"] += 1
            continue
        word = min(candidates, key=lambda w: abs(w.left - int(bbox[0])))
        crop = Image.open(img_path).convert("L").crop((word.left, word.top, word.left + word.width, word.top + word.height))

        # Hard leakage guard: no glyph from the test article/subnr may classify it.
        needle = f"-sub{subnr}-"
        refs = [p for p in all_refs if needle not in p.name]
        ref_classes = {_label(p) for p in refs}
        if any(ch not in ref_classes for ch in expected):
            skipped["missing-class-after-holdout"] += 1
            continue

        segments = _segment_word(crop, len(expected))
        if len(segments) != len(expected):
            skipped["segment-count"] += 1
            continue

        pred_chars = []
        margins = []
        accepted = True
        for _x0, _x1, glyph in segments:
            pred, _score, margin = _best_class(glyph, refs, args.max_shift)
            if pred is None or (margin is not None and margin < args.margin):
                pred_chars.append("?")
                accepted = False
            else:
                pred_chars.append(pred)
            margins.append(None if margin is None else round(margin, 6))

        pred_text = "".join(pred_chars)
        n_correct = sum(a == b for a, b in zip(pred_text, expected))
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
            "margins": margins,
            "word_bbox": [word.left, word.top, word.width, word.height],
            "same_subnr_refs_excluded": True,
        })

    payload = {
        "style": args.style,
        "library": str(args.library),
        "template_count": len(all_refs),
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
            "leakage_guard": "all templates from test subnr excluded",
            "segmentation": "x-ink groups with expected-length valley splitting",
        },
    }
    json.dump(payload, __import__("sys").stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
