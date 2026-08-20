from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from PIL import Image, ImageChops


@dataclass(frozen=True)
class GlyphComparison:
    candidate: str
    template: str
    score: float


def _trim(img: Image.Image) -> Image.Image:
    gray = img.convert("L")
    inv = ImageChops.invert(gray)
    bbox = inv.getbbox()
    return gray.crop(bbox) if bbox else gray


def _score(observed: Image.Image, template: Image.Image) -> float:
    obs = _trim(observed)
    ref = _trim(template)
    if obs.width == 0 or obs.height == 0 or ref.width == 0 or ref.height == 0:
        return 1.0
    ref = ref.resize(obs.size, Image.Resampling.LANCZOS)
    diff = ImageChops.difference(obs, ref)
    vals = list(diff.getdata())
    return sum(vals) / (255.0 * len(vals)) if vals else 1.0


def _find_word_bbox(tsv: Path, target: str) -> tuple[int, int, int, int]:
    with tsv.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        for row in reader:
            if row.get("level") != "5" or row.get("text") != target:
                continue
            return int(row["left"]), int(row["top"]), int(row["width"]), int(row["height"])
    raise SystemExit(f"word not found in TSV: {target}")


def _segment_by_index(word_crop: Image.Image, text: str, index: int) -> Image.Image:
    """Approximate one glyph by proportional x slicing.

    This is deliberately simple and only intended for ambiguous-character fallback.
    The surrounding word bbox is already localized by OCR; later we can replace
    this with connected-component segmentation if needed.
    """
    n = max(1, len(text))
    left = round(word_crop.width * index / n)
    right = round(word_crop.width * (index + 1) / n)
    pad = max(1, round(word_crop.width / n * 0.25))
    left = max(0, left - pad)
    right = min(word_crop.width, right + pad)
    return word_crop.crop((left, 0, max(left + 1, right), word_crop.height))


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare one ambiguous OCR glyph with real SAOL glyph templates.")
    parser.add_argument("image", type=Path)
    parser.add_argument("tsv", type=Path)
    parser.add_argument("--word", required=True, help="OCR word containing the ambiguous glyph")
    parser.add_argument("--index", type=int, required=True, help="0-based character index in OCR word")
    parser.add_argument("--templates", type=Path, required=True)
    args = parser.parse_args()

    x, y, w, h = _find_word_bbox(args.tsv, args.word)
    page = Image.open(args.image).convert("L")
    word_crop = page.crop((x, y, x + w, y + h))
    observed = _segment_by_index(word_crop, args.word, args.index)

    comparisons: list[GlyphComparison] = []
    for path in sorted(args.templates.glob("*.png")):
        candidate = path.name.split("-", 1)[0]
        template = Image.open(path).convert("L")
        comparisons.append(GlyphComparison(candidate, path.name, round(_score(observed, template), 6)))

    comparisons.sort(key=lambda item: item.score)
    best = comparisons[0] if comparisons else None
    second = comparisons[1] if len(comparisons) > 1 else None
    margin = None if best is None or second is None else round(second.score - best.score, 6)

    json.dump(
        {
            "word": args.word,
            "index": args.index,
            "ocr_character": args.word[args.index] if 0 <= args.index < len(args.word) else None,
            "word_bbox": [x, y, w, h],
            "best": asdict(best) if best else None,
            "margin": margin,
            "comparisons": [asdict(item) for item in comparisons],
        },
        __import__("sys").stdout,
        ensure_ascii=False,
        indent=2,
    )
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
