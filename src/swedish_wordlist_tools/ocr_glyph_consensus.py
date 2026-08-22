from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from statistics import median

from PIL import Image, ImageChops


def _label_from_filename(path: Path) -> str:
    raw = path.stem.split("-", 1)[0]
    if raw.startswith("u") and len(raw) == 5:
        try:
            return chr(int(raw[1:], 16))
        except ValueError:
            pass
    return raw


def _safe_label(ch: str) -> str:
    return ch if ch.isalnum() else f"u{ord(ch):04x}"


def _canvas(image: Image.Image, width: int, height: int, dx: int = 0, dy: int = 0) -> Image.Image:
    out = Image.new("L", (width, height), 255)
    x = (width - image.width) // 2 + dx
    y = (height - image.height) // 2 + dy
    out.paste(image, (x, y))
    return out


def _score(a: Image.Image, b: Image.Image) -> float:
    diff = ImageChops.difference(a, b)
    vals = list(diff.getdata())
    return sum(vals) / max(1, len(vals))


def _ink_crop(image: Image.Image, threshold: int = 245) -> Image.Image:
    pix = image.load()
    xs: list[int] = []
    ys: list[int] = []
    for y in range(image.height):
        for x in range(image.width):
            if pix[x, y] < threshold:
                xs.append(x)
                ys.append(y)
    if not xs:
        return image
    return image.crop((min(xs), min(ys), max(xs) + 1, max(ys) + 1))


def _median_image(images: list[Image.Image], max_shift: int) -> tuple[Image.Image, list[dict[str, object]]]:
    max_w = max(im.width for im in images)
    max_h = max(im.height for im in images)
    width = max_w + max_shift * 2 + 2
    height = max_h + max_shift * 2 + 2

    # Use the image closest to the median dimensions as a stable reference.
    med_w = median([im.width for im in images])
    med_h = median([im.height for im in images])
    ref_idx = min(range(len(images)), key=lambda i: abs(images[i].width - med_w) + abs(images[i].height - med_h))
    ref = _canvas(images[ref_idx], width, height)

    aligned: list[Image.Image] = []
    placements: list[dict[str, object]] = []
    for idx, image in enumerate(images):
        best = None
        for dy in range(-max_shift, max_shift + 1):
            for dx in range(-max_shift, max_shift + 1):
                candidate = _canvas(image, width, height, dx, dy)
                score = _score(candidate, ref)
                if best is None or score < best[0]:
                    best = (score, dx, dy, candidate)
        assert best is not None
        score, dx, dy, candidate = best
        aligned.append(candidate)
        placements.append({"index": idx, "dx": dx, "dy": dy, "score_to_reference": round(score, 6)})

    result = Image.new("L", (width, height), 255)
    out = result.load()
    loaded = [im.load() for im in aligned]
    for y in range(height):
        for x in range(width):
            out[x, y] = int(round(median([pix[x, y] for pix in loaded])))
    return _ink_crop(result), placements


def main() -> int:
    parser = argparse.ArgumentParser(description="Build aligned median consensus glyphs from a reviewed SAOL glyph library.")
    parser.add_argument("library", type=Path)
    parser.add_argument("--style", choices=("italic", "bold", "roman"))
    parser.add_argument("--max-shift", type=int, default=3)
    parser.add_argument("--min-examples", type=int, default=2)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()

    styles = [args.style] if args.style else [s for s in ("italic", "bold", "roman") if (args.library / s).is_dir()]
    args.out_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, object] = {"max_shift": args.max_shift, "min_examples": args.min_examples, "styles": {}}

    for style in styles:
        groups: dict[str, list[Path]] = defaultdict(list)
        for path in sorted((args.library / style).glob("*.png")):
            groups[_label_from_filename(path)].append(path)
        style_out = args.out_dir / style
        style_out.mkdir(parents=True, exist_ok=True)
        style_manifest: dict[str, object] = {}
        for label, paths in sorted(groups.items()):
            if len(paths) < args.min_examples:
                continue
            images: list[Image.Image] = []
            for path in paths:
                with Image.open(path) as im0:
                    images.append(im0.convert("L").copy())
            consensus, placements = _median_image(images, args.max_shift)
            output = style_out / f"{_safe_label(label)}-consensus-{len(paths):03d}.png"
            consensus.save(output)
            style_manifest[label] = {
                "count": len(paths),
                "output": str(output.relative_to(args.out_dir)),
                "sources": [str(p.relative_to(args.library)) for p in paths],
                "placements": placements,
            }
        manifest["styles"][style] = style_manifest

    (args.out_dir / "manifest-consensus.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    json.dump(manifest, __import__("sys").stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
