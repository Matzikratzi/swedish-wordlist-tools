from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

from PIL import Image, ImageChops, ImageFont


@dataclass(frozen=True)
class CandidateScore:
    candidate: str
    font: str
    size: int
    score: float


def _find_fonts(pattern: str) -> list[str]:
    out = subprocess.check_output(["fc-match", "-f", "%{file}\n", pattern], text=True)
    return [line.strip() for line in out.splitlines() if line.strip()]


def _trim(img: Image.Image) -> Image.Image:
    # Convert to black ink on white background and trim whitespace.
    gray = img.convert("L")
    inv = ImageChops.invert(gray)
    bbox = inv.getbbox()
    return gray.crop(bbox) if bbox else gray


def _render(candidate: str, font_path: str, size: int) -> Image.Image:
    font = ImageFont.truetype(font_path, size=size)
    bbox = font.getbbox(candidate)
    w = max(1, bbox[2] - bbox[0] + 8)
    h = max(1, bbox[3] - bbox[1] + 8)
    img = Image.new("L", (w, h), 255)
    from PIL import ImageDraw

    draw = ImageDraw.Draw(img)
    draw.text((4 - bbox[0], 4 - bbox[1]), candidate, fill=0, font=font)
    return _trim(img)


def _fit_score(observed: Image.Image, rendered: Image.Image) -> float:
    obs = _trim(observed)
    if obs.width == 0 or obs.height == 0 or rendered.width == 0 or rendered.height == 0:
        return 1.0
    # Resize rendered glyph to observed crop. This deliberately ignores absolute
    # point size; the outer loop still reports which nominal font size produced it.
    test = rendered.resize(obs.size, Image.Resampling.LANCZOS)
    diff = ImageChops.difference(obs, test)
    vals = list(diff.getdata())
    return sum(vals) / (255.0 * len(vals)) if vals else 1.0


def main() -> int:
    parser = argparse.ArgumentParser(description="Experimentally compare an observed SAOL glyph crop with rendered candidates.")
    parser.add_argument("image", type=Path)
    parser.add_argument("--bbox", required=True, help="x,y,w,h in image coordinates")
    parser.add_argument("--candidates", default="ce", help="candidate glyphs, e.g. ce")
    parser.add_argument("--font-patterns", default="serif:style=Bold,serif:style=Regular,serif:style=Italic")
    parser.add_argument("--sizes", default="10,11,12,13,14,15,16,17,18")
    args = parser.parse_args()

    x, y, w, h = (int(part) for part in args.bbox.split(","))
    page = Image.open(args.image).convert("L")
    observed = page.crop((x, y, x + w, y + h))

    patterns = [p.strip() for p in args.font_patterns.split(",") if p.strip()]
    font_paths: list[str] = []
    for pattern in patterns:
        for path in _find_fonts(pattern):
            if path not in font_paths:
                font_paths.append(path)

    sizes = [int(s) for s in args.sizes.split(",") if s.strip()]
    scores: list[CandidateScore] = []
    for font_path in font_paths:
        for size in sizes:
            for candidate in args.candidates:
                rendered = _render(candidate, font_path, size)
                score = _fit_score(observed, rendered)
                scores.append(CandidateScore(candidate, font_path, size, round(score, 6)))

    scores.sort(key=lambda item: item.score)
    json.dump(
        {
            "bbox": [x, y, w, h],
            "candidates": args.candidates,
            "best": [asdict(item) for item in scores[:20]],
        },
        __import__("sys").stdout,
        ensure_ascii=False,
        indent=2,
    )
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
