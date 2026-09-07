from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path

from PIL import Image


@dataclass(frozen=True)
class WordBox:
    text: str
    left: int
    top: int
    width: int
    height: int
    confidence: float


def load_words(tsv_path: Path) -> list[WordBox]:
    words: list[WordBox] = []
    with tsv_path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        for row in reader:
            if row.get("level") != "5" or not row.get("text"):
                continue
            words.append(
                WordBox(
                    text=row["text"],
                    left=int(row["left"]),
                    top=int(row["top"]),
                    width=int(row["width"]),
                    height=int(row["height"]),
                    confidence=float(row["conf"]),
                )
            )
    return words


def stats_for_box(image: Image.Image, word: WordBox, threshold: int = 200) -> dict[str, float | int | str]:
    crop = image.crop((word.left, word.top, word.left + word.width, word.top + word.height)).convert("L")
    pixels = list(crop.getdata())
    total = len(pixels) or 1
    dark = sum(1 for p in pixels if p < threshold)
    very_dark = sum(1 for p in pixels if p < 96)
    mean = sum(pixels) / total
    return {
        "text": word.text,
        "left": word.left,
        "top": word.top,
        "width": word.width,
        "height": word.height,
        "confidence": round(word.confidence, 2),
        "dark_ratio": round(dark / total, 4),
        "very_dark_ratio": round(very_dark / total, 4),
        "mean_gray": round(mean, 2),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure simple grayscale statistics in Tesseract word bounding boxes.")
    parser.add_argument("image", type=Path)
    parser.add_argument("tsv", type=Path)
    parser.add_argument("patterns", nargs="+", help="Case-insensitive substrings of OCR words to report")
    args = parser.parse_args()

    image = Image.open(args.image)
    patterns = [p.casefold() for p in args.patterns]
    matches = [w for w in load_words(args.tsv) if any(p in w.text.casefold() for p in patterns)]

    if not matches:
        print("No matching OCR words found.")
        return 1

    print("text\tx\ty\tw\th\tconf\tdark\tvery_dark\tmean_gray")
    for word in matches:
        s = stats_for_box(image, word)
        print(
            f"{s['text']}\t{s['left']}\t{s['top']}\t{s['width']}\t{s['height']}\t"
            f"{s['confidence']}\t{s['dark_ratio']}\t{s['very_dark_ratio']}\t{s['mean_gray']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
