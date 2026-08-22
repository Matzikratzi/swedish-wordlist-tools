from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image

from .ocr_glyph_leave_one_out import _label, _shift_score


def _evaluate_one(query: Path, refs: list[Path], max_shift: int) -> dict[str, object]:
    truth = _label(query)
    qimg = Image.open(query).convert("L")
    best_by_class: dict[str, dict[str, object]] = {}
    nearest: list[dict[str, object]] = []
    for ref in refs:
        rimg = Image.open(ref).convert("L")
        score, dx, dy = _shift_score(qimg, rimg, max_shift)
        row = {
            "candidate": _label(ref),
            "template": ref.name,
            "score": round(score, 6),
            "dx": dx,
            "dy": dy,
        }
        nearest.append(row)
        prev = best_by_class.get(row["candidate"])
        if prev is None or float(row["score"]) < float(prev["score"]):
            best_by_class[str(row["candidate"])] = row
    nearest.sort(key=lambda x: float(x["score"]))
    classes = sorted(best_by_class.values(), key=lambda x: float(x["score"]))
    best = classes[0] if classes else None
    second = classes[1] if len(classes) > 1 else None
    margin = None
    if best is not None and second is not None:
        margin = round(float(second["score"]) - float(best["score"]), 6)
    pred = str(best["candidate"]) if best is not None else None
    return {
        "query": query.name,
        "truth": truth,
        "prediction": pred,
        "correct": pred == truth,
        "best": best,
        "second_class": second,
        "margin": margin,
        "nearest": nearest[:8],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Hold-out validation for SAOL glyph classification.")
    ap.add_argument("templates", type=Path)
    ap.add_argument("--style", choices=("italic", "bold", "roman"), required=True)
    ap.add_argument("--max-shift", type=int, default=3)
    ap.add_argument("--thresholds", default="0,0.005,0.01,0.02,0.03")
    args = ap.parse_args()

    paths = sorted((args.templates / args.style).glob("*.png"))
    counts = Counter(_label(p) for p in paths)
    evaluable = [p for p in paths if counts[_label(p)] >= 2]
    results = []
    per_char: dict[str, dict[str, int]] = defaultdict(lambda: {"correct": 0, "total": 0})
    for query in evaluable:
        refs = [p for p in paths if p != query]
        row = _evaluate_one(query, refs, args.max_shift)
        results.append(row)
        st = per_char[str(row["truth"])]
        st["total"] += 1
        st["correct"] += int(bool(row["correct"]))

    thresholds = [float(x) for x in args.thresholds.split(",") if x.strip()]
    calibration = []
    for t in thresholds:
        accepted = [r for r in results if r["margin"] is None or float(r["margin"]) >= t]
        correct = sum(bool(r["correct"]) for r in accepted)
        calibration.append({
            "margin_threshold": t,
            "accepted": len(accepted),
            "coverage": round(len(accepted) / len(results), 4) if results else None,
            "correct": correct,
            "precision": round(correct / len(accepted), 4) if accepted else None,
        })

    margins_correct = sorted(float(r["margin"]) for r in results if r["correct"] and r["margin"] is not None)
    margins_wrong = sorted(float(r["margin"]) for r in results if not r["correct"] and r["margin"] is not None)
    payload = {
        "style": args.style,
        "template_count": len(paths),
        "class_count": len(counts),
        "evaluable": len(results),
        "correct": sum(bool(r["correct"]) for r in results),
        "accuracy": round(sum(bool(r["correct"]) for r in results) / len(results), 4) if results else None,
        "max_shift": args.max_shift,
        "per_char": {
            ch: {**st, "accuracy": round(st["correct"] / st["total"], 4) if st["total"] else None}
            for ch, st in sorted(per_char.items())
        },
        "calibration": calibration,
        "margin_summary": {
            "correct_min": margins_correct[0] if margins_correct else None,
            "correct_median": margins_correct[len(margins_correct)//2] if margins_correct else None,
            "wrong_max": margins_wrong[-1] if margins_wrong else None,
        },
        "errors": [r for r in results if not r["correct"]],
        "results": results,
    }
    json.dump(payload, __import__("sys").stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
