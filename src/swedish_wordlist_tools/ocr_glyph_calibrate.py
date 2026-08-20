from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from PIL import Image, ImageChops


@dataclass(frozen=True)
class GlyphSample:
    text: str
    bbox: tuple[int, int, int, int]
    dark_ratio: float
    mean_gray: float
    accepted: bool
    reject_reason: str | None


def _trim(img: Image.Image) -> Image.Image:
    gray = img.convert("L")
    inv = ImageChops.invert(gray)
    bbox = inv.getbbox()
    return gray.crop(bbox) if bbox else gray


def _stats(img: Image.Image) -> tuple[float, float]:
    gray = _trim(img)
    vals = list(gray.getdata())
    if not vals:
        return 0.0, 255.0
    dark = sum(1 for v in vals if v < 200) / len(vals)
    mean = sum(vals) / len(vals)
    return dark, mean


def _quality_reason(height: int, dark_ratio: float, *, max_height: int, min_dark_ratio: float) -> str | None:
    if height > max_height:
        return f"bbox-too-tall>{max_height}"
    if dark_ratio < min_dark_ratio:
        return f"dark-ratio<{min_dark_ratio}"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Collect real SAOL word crops for font/style calibration while rejecting merged OCR boxes."
    )
    parser.add_argument("image", type=Path)
    parser.add_argument("tsv", type=Path)
    parser.add_argument("targets", nargs="+", help="OCR word strings to collect exactly")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--max-height", type=int, default=18, help="Reject suspiciously tall word boxes")
    parser.add_argument(
        "--min-dark-ratio",
        type=float,
        default=0.28,
        help="Reject low-density boxes when calibrating bold headword style",
    )
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    page = Image.open(args.image).convert("L")
    wanted = set(args.targets)
    samples: list[GlyphSample] = []

    with args.tsv.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        for row in reader:
            if row.get("level") != "5":
                continue
            text = row.get("text", "")
            if text not in wanted:
                continue
            x = int(row["left"])
            y = int(row["top"])
            w = int(row["width"])
            h = int(row["height"])
            crop = page.crop((x, y, x + w, y + h))
            dark_ratio, mean_gray = _stats(crop)
            reject_reason = _quality_reason(
                h,
                dark_ratio,
                max_height=args.max_height,
                min_dark_ratio=args.min_dark_ratio,
            )
            accepted = reject_reason is None
            index = len(samples)
            suffix = "accepted" if accepted else "rejected"
            crop.save(args.out_dir / f"{index:03d}-{suffix}-{text.replace('/', '_')}.png")
            samples.append(
                GlyphSample(
                    text=text,
                    bbox=(x, y, w, h),
                    dark_ratio=round(dark_ratio, 4),
                    mean_gray=round(mean_gray, 2),
                    accepted=accepted,
                    reject_reason=reject_reason,
                )
            )

    json.dump([asdict(s) for s in samples], __import__("sys").stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
