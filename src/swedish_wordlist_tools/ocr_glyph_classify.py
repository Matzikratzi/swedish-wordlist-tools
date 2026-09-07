from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from PIL import Image

from .ocr_glyph_leave_one_out import _label, _shift_score


@dataclass(frozen=True)
class Match:
    candidate: str
    template: str
    score: float
    dx: int
    dy: int


def classify_glyph(
    query: Image.Image,
    template_root: Path,
    style: str,
    max_shift: int = 3,
    top: int = 8,
    require_margin: float = 0.0,
) -> dict[str, object]:
    root = template_root / style
    paths = sorted(root.glob("*.png"))
    if not paths:
        return {
            "status": "no-templates",
            "style": style,
            "template_count": 0,
            "prediction": None,
        }

    nearest: list[Match] = []
    best_by_class: dict[str, Match] = {}
    for path in paths:
        ref = Image.open(path).convert("L")
        score, dx, dy = _shift_score(query, ref, max_shift)
        item = Match(_label(path), path.name, round(score, 6), dx, dy)
        nearest.append(item)
        prev = best_by_class.get(item.candidate)
        if prev is None or item.score < prev.score:
            best_by_class[item.candidate] = item

    nearest.sort(key=lambda m: m.score)
    classes = sorted(best_by_class.values(), key=lambda m: m.score)
    best = classes[0] if classes else None
    second = classes[1] if len(classes) > 1 else None
    margin = None
    if best is not None and second is not None:
        margin = round(second.score - best.score, 6)

    accepted = best is not None and (margin is None or margin >= require_margin)
    return {
        "status": "accepted" if accepted else "uncertain",
        "style": style,
        "template_count": len(paths),
        "class_count": len(classes),
        "prediction": best.candidate if accepted and best is not None else None,
        "best": asdict(best) if best else None,
        "second_class": asdict(second) if second else None,
        "margin": margin,
        "require_margin": require_margin,
        "nearest": [asdict(m) for m in nearest[:top]],
        "best_by_class": [asdict(m) for m in classes[:top]],
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Classify one SAOL glyph by translation-only pixel matching against a style-specific template library."
    )
    ap.add_argument("glyph", type=Path)
    ap.add_argument("templates", type=Path)
    ap.add_argument("--style", choices=("italic", "bold", "roman"), required=True)
    ap.add_argument("--max-shift", type=int, default=3)
    ap.add_argument("--top", type=int, default=8)
    ap.add_argument(
        "--require-margin",
        type=float,
        default=0.0,
        help="Reject prediction when second-best class is closer than this score margin.",
    )
    args = ap.parse_args()

    query = Image.open(args.glyph).convert("L")
    result = classify_glyph(
        query,
        args.templates,
        args.style,
        max_shift=args.max_shift,
        top=args.top,
        require_margin=args.require_margin,
    )
    result["glyph"] = str(args.glyph)
    json.dump(result, __import__("sys").stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
