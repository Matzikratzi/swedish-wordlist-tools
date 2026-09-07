from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from PIL import Image, ImageChops


@dataclass(frozen=True)
class TemplateSample:
    source_word: str
    character: str
    char_index: int
    style: str
    bbox: tuple[int, int, int, int]
    output: str


def _trim(img: Image.Image) -> Image.Image:
    gray = img.convert("L")
    inv = ImageChops.invert(gray)
    bbox = inv.getbbox()
    return gray.crop(bbox) if bbox else gray


def _ink_projection(gray: Image.Image) -> list[float]:
    img = _trim(gray)
    if img.width <= 0:
        return []
    out: list[float] = []
    for x in range(img.width):
        total = 0.0
        for y in range(img.height):
            total += (255 - img.getpixel((x, y))) / 255.0
        out.append(total)
    return out


def _split_by_projection(crop: Image.Image, n_chars: int) -> list[tuple[int, int]]:
    img = _trim(crop)
    if n_chars <= 0 or img.width <= 0:
        return []
    if n_chars == 1:
        return [(0, img.width)]

    proj = _ink_projection(img)
    expected = img.width / n_chars
    cuts = [0]
    last = 0
    for i in range(1, n_chars):
        target = i * expected
        radius = max(1, round(expected * 0.45))
        lo = max(last + 1, round(target) - radius)
        hi = min(img.width - 1, round(target) + radius)
        if lo >= hi:
            cut = max(last + 1, min(img.width - 1, round(target)))
        else:
            cut = min(range(lo, hi + 1), key=lambda x: proj[x])
        cuts.append(cut)
        last = cut
    cuts.append(img.width)
    return [(cuts[i], cuts[i + 1]) for i in range(len(cuts) - 1)]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract approximate per-character templates from accepted real SAOL word crops."
    )
    parser.add_argument("image", type=Path)
    parser.add_argument("tsv", type=Path)
    parser.add_argument("targets", nargs="+", help="Exact OCR word strings known to be clean/accepted")
    parser.add_argument("--chars", default="ce", help="Only save these character classes")
    parser.add_argument("--style", choices=("bold", "italic", "roman"), required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()

    style_dir = args.out_dir / args.style
    style_dir.mkdir(parents=True, exist_ok=True)
    page = Image.open(args.image).convert("L")
    wanted_words = set(args.targets)
    wanted_chars = set(args.chars)
    samples: list[TemplateSample] = []

    with args.tsv.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        for row in reader:
            if row.get("level") != "5":
                continue
            text = row.get("text", "")
            if text not in wanted_words:
                continue
            x = int(row["left"])
            y = int(row["top"])
            w = int(row["width"])
            h = int(row["height"])
            if h > 18 or h < 8:
                continue
            crop = _trim(page.crop((x, y, x + w, y + h)))
            spans = _split_by_projection(crop, len(text))
            if len(spans) != len(text):
                continue
            for i, ch in enumerate(text):
                if ch not in wanted_chars:
                    continue
                left, right = spans[i]
                if right <= left:
                    continue
                glyph = _trim(crop.crop((left, 0, right, crop.height)))
                if glyph.width <= 0 or glyph.height <= 0:
                    continue
                filename = f"{ch}-{len(samples):04d}-{text}-{i}.png".replace("/", "_")
                glyph.save(style_dir / filename)
                samples.append(
                    TemplateSample(
                        source_word=text,
                        character=ch,
                        char_index=i,
                        style=args.style,
                        bbox=(x + left, y, right - left, h),
                        output=str(Path(args.style) / filename),
                    )
                )

    json.dump([asdict(s) for s in samples], __import__("sys").stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
