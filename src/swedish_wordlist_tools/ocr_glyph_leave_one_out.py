from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from PIL import Image, ImageChops


@dataclass(frozen=True)
class Neighbor:
    candidate: str
    template: str
    score: float
    dx: int
    dy: int


def _trim(img: Image.Image) -> Image.Image:
    gray = img.convert("L")
    inv = ImageChops.invert(gray)
    bbox = inv.getbbox()
    return gray.crop(bbox) if bbox else gray


def _label(path: Path) -> str:
    stem = path.name.split("-", 1)[0]
    if stem.startswith("u") and len(stem) == 5:
        try:
            return chr(int(stem[1:], 16))
        except ValueError:
            pass
    return stem


def _ink(img: Image.Image) -> Image.Image:
    return ImageChops.invert(_trim(img))


def _shift_score(a: Image.Image, b: Image.Image, max_shift: int) -> tuple[float, int, int]:
    """Compare glyphs without rescaling, allowing only small x/y translation.

    Both glyphs are placed on a shared white canvas.  The score is mean absolute
    grayscale error over the union canvas; lower is better.  This deliberately
    tests the hypothesis that SAOL glyph rasters are stable and merely move by a
    few pixels between occurrences.
    """
    aa = _ink(a)
    bb = _ink(b)
    if aa.width == 0 or aa.height == 0 or bb.width == 0 or bb.height == 0:
        return 1.0, 0, 0

    pad = max_shift + 2
    width = max(aa.width, bb.width) + 2 * pad
    height = max(aa.height, bb.height) + 2 * pad

    base = Image.new("L", (width, height), 0)
    base.paste(aa, (pad, pad))

    best = (1.0, 0, 0)
    for dy in range(-max_shift, max_shift + 1):
        for dx in range(-max_shift, max_shift + 1):
            other = Image.new("L", (width, height), 0)
            other.paste(bb, (pad + dx, pad + dy))
            diff = ImageChops.difference(base, other)
            vals = list(diff.getdata())
            score = sum(vals) / (255.0 * len(vals)) if vals else 1.0
            if score < best[0]:
                best = (score, dx, dy)
    return best


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Leave-one-out validation of a real SAOL glyph library using translation-only pixel matching."
    )
    parser.add_argument("templates", type=Path)
    parser.add_argument("--style", choices=("italic", "bold", "roman"), default="italic")
    parser.add_argument("--max-shift", type=int, default=3)
    parser.add_argument("--limit", type=int, default=0, help="Maximum query glyphs; 0 means all")
    parser.add_argument("--top", type=int, default=5, help="Nearest neighbors shown per query")
    args = parser.parse_args()

    root = args.templates / args.style
    paths = sorted(root.glob("*.png"))
    if args.limit > 0:
        queries = paths[: args.limit]
    else:
        queries = paths

    cache = {path: Image.open(path).convert("L") for path in paths}
    results = []
    correct = 0
    evaluable = 0
    per_char: dict[str, dict[str, int]] = {}

    labels = [_label(path) for path in paths]
    label_counts: dict[str, int] = {}
    for label in labels:
        label_counts[label] = label_counts.get(label, 0) + 1

    for query in queries:
        truth = _label(query)
        # A class with only one example cannot be tested leave-one-out.
        if label_counts.get(truth, 0) < 2:
            continue
        evaluable += 1
        neighbors: list[Neighbor] = []
        for ref in paths:
            if ref == query:
                continue
            score, dx, dy = _shift_score(cache[query], cache[ref], args.max_shift)
            neighbors.append(Neighbor(_label(ref), ref.name, round(score, 6), dx, dy))
        neighbors.sort(key=lambda item: item.score)
        predicted = neighbors[0].candidate if neighbors else None
        ok = predicted == truth
        if ok:
            correct += 1
        stats = per_char.setdefault(truth, {"correct": 0, "total": 0})
        stats["total"] += 1
        stats["correct"] += int(ok)
        best_same = next((n for n in neighbors if n.candidate == truth), None)
        best_other = next((n for n in neighbors if n.candidate != truth), None)
        margin = None
        if best_same is not None and best_other is not None:
            margin = round(best_other.score - best_same.score, 6)
        results.append(
            {
                "query": query.name,
                "truth": truth,
                "predicted": predicted,
                "correct": ok,
                "best_same": asdict(best_same) if best_same else None,
                "best_other": asdict(best_other) if best_other else None,
                "margin": margin,
                "nearest": [asdict(item) for item in neighbors[: args.top]],
            }
        )

    payload = {
        "style": args.style,
        "template_count": len(paths),
        "evaluable": evaluable,
        "correct": correct,
        "accuracy": round(correct / evaluable, 4) if evaluable else None,
        "max_shift": args.max_shift,
        "per_char": {
            ch: {**stats, "accuracy": round(stats["correct"] / stats["total"], 4) if stats["total"] else None}
            for ch, stats in sorted(per_char.items())
        },
        "errors": [item for item in results if not item["correct"]][:20],
        "results": results,
    }
    json.dump(payload, __import__("sys").stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
