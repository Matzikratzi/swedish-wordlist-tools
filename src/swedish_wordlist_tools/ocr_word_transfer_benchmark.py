from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image

from .ocr_glyph_leave_one_out import _label, _shift_score
from .ocr_tsv_articles import read_words
from .ocr_word_glyph_read import _segment_word


def _best_class(query: Image.Image, refs: list[Path], max_shift: int) -> dict[str, object]:
    best_by_class: dict[str, dict[str, object]] = {}
    for ref in refs:
        score, dx, dy = _shift_score(query, Image.open(ref).convert("L"), max_shift)
        ch = _label(ref)
        row = {
            "character": ch,
            "template": ref.name,
            "score": round(score, 6),
            "dx": dx,
            "dy": dy,
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
    return {
        "best": best,
        "second": second,
        "margin": margin,
        "ranked": ranked,
    }


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

    all_refs = sorted((args.library / args.style).glob("*.png"))
    results = []
    skipped = Counter()
    char_total = char_correct = word_correct = 0

    if args.diagnostics_out:
        args.diagnostics_out.mkdir(parents=True, exist_ok=True)

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

        needle = f"-sub{subnr}-"
        refs = [p for p in all_refs if needle not in p.name]
        ref_classes = {_label(p) for p in refs}
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
            safe_expected = "".join(ch if ch.isalnum() else f"u{ord(ch):04x}" for ch in expected)
            word_dir = args.diagnostics_out / f"sub{subnr}-p{page}-c{column}-{safe_expected}"
            word_dir.mkdir(parents=True, exist_ok=True)
            crop.save(word_dir / "word.png")

        pred_chars = []
        margins = []
        segment_rows = []
        accepted = True
        for i, (x0, x1, glyph) in enumerate(segments):
            match = _best_class(glyph, refs, args.max_shift)
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
            "word_bbox": [word.left, word.top, word.width, word.height],
            "same_subnr_refs_excluded": True,
            "diagnostic_dir": str(word_dir) if word_dir is not None else None,
            "segments": segment_rows,
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
            "diagnostics": "optional word and segment crops plus best/second reference metadata",
        },
    }
    json.dump(payload, __import__("sys").stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
