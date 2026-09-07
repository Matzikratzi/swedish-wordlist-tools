from __future__ import annotations

import argparse
import csv
import json
import statistics
from dataclasses import asdict, dataclass
from pathlib import Path

from PIL import Image, ImageChops


@dataclass(frozen=True)
class GlyphComparison:
    candidate: str
    template: str
    score: float


@dataclass(frozen=True)
class CandidateSummary:
    candidate: str
    template_count: int
    used_count: int
    best_score: float
    median_top_score: float
    mean_top_score: float


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


def _row_ink(gray: Image.Image) -> list[float]:
    return [sum((255 - gray.getpixel((x, y))) / 255.0 for x in range(gray.width)) for y in range(gray.height)]


def _dominant_text_band(word_crop: Image.Image, expected_height: int = 12) -> tuple[int, int]:
    gray = word_crop.convert("L")
    if gray.height <= expected_height + 2:
        return 0, gray.height
    ink = _row_ink(gray)
    min_h = max(8, expected_height - 3)
    max_h = min(gray.height, expected_height + 4)
    best = (0, min(gray.height, expected_height))
    best_score = -1.0
    for h in range(min_h, max_h + 1):
        for top in range(0, gray.height - h + 1):
            score = sum(ink[top : top + h])
            if score > best_score:
                best_score = score
                best = (top, top + h)
    return best


def _col_ink(gray: Image.Image) -> list[float]:
    return [sum((255 - gray.getpixel((x, y))) / 255.0 for y in range(gray.height)) for x in range(gray.width)]


def _segment_by_projection(word_crop: Image.Image, text: str, index: int) -> tuple[Image.Image, tuple[int, int, int, int]]:
    top, bottom = _dominant_text_band(word_crop)
    band = _trim(word_crop.crop((0, top, word_crop.width, bottom)))
    n = max(1, len(text))
    if index < 0 or index >= n:
        raise SystemExit(f"index {index} outside word of length {n}")
    if n == 1:
        return band, (0, top, band.width, bottom - top)

    proj = _col_ink(band)
    expected = band.width / n
    cuts = [0]
    last = 0
    for i in range(1, n):
        target = i * expected
        radius = max(1, round(expected * 0.45))
        lo = max(last + 1, round(target) - radius)
        hi = min(band.width - 1, round(target) + radius)
        if lo >= hi:
            cut = max(last + 1, min(band.width - 1, round(target)))
        else:
            cut = min(range(lo, hi + 1), key=lambda x: proj[x])
        cuts.append(cut)
        last = cut
    cuts.append(band.width)

    left, right = cuts[index], cuts[index + 1]
    pad = 1
    left = max(0, left - pad)
    right = min(band.width, right + pad)
    glyph = _trim(band.crop((left, 0, max(left + 1, right), band.height)))
    return glyph, (left, top, right - left, bottom - top)


def _summaries(comparisons: list[GlyphComparison], top_k: int) -> list[CandidateSummary]:
    grouped: dict[str, list[float]] = {}
    for item in comparisons:
        grouped.setdefault(item.candidate, []).append(item.score)
    result: list[CandidateSummary] = []
    for candidate, scores in grouped.items():
        ordered = sorted(scores)
        chosen = ordered[: max(1, min(top_k, len(ordered)))]
        result.append(
            CandidateSummary(
                candidate=candidate,
                template_count=len(ordered),
                used_count=len(chosen),
                best_score=round(ordered[0], 6),
                median_top_score=round(statistics.median(chosen), 6),
                mean_top_score=round(sum(chosen) / len(chosen), 6),
            )
        )
    return sorted(result, key=lambda item: (item.median_top_score, item.mean_top_score, item.best_score))


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare one ambiguous OCR glyph with real SAOL glyph templates.")
    parser.add_argument("image", type=Path)
    parser.add_argument("tsv", type=Path)
    parser.add_argument("--word", required=True)
    parser.add_argument("--index", type=int, required=True)
    parser.add_argument("--templates", type=Path, required=True)
    parser.add_argument("--style", choices=("bold", "italic", "roman"), required=True)
    parser.add_argument("--top-k", type=int, default=7, help="Nearest templates per character used for ensemble score")
    parser.add_argument("--observed-out", type=Path)
    parser.add_argument("--context-out", type=Path)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()

    x, y, w, h = _find_word_bbox(args.tsv, args.word)
    page = Image.open(args.image).convert("L")
    word_crop = page.crop((x, y, x + w, y + h))
    observed, local_bbox = _segment_by_projection(word_crop, args.word, args.index)

    observed_path = None
    if args.observed_out is not None:
        args.observed_out.parent.mkdir(parents=True, exist_ok=True)
        observed.save(args.observed_out)
        observed_path = str(args.observed_out.resolve())

    context_path = None
    if args.context_out is not None:
        args.context_out.parent.mkdir(parents=True, exist_ok=True)
        pad_x, pad_y = 12, 8
        context = page.crop((max(0, x - pad_x), max(0, y - pad_y), min(page.width, x + w + pad_x), min(page.height, y + h + pad_y)))
        context.save(args.context_out)
        context_path = str(args.context_out.resolve())

    template_dir = args.templates / args.style
    comparisons: list[GlyphComparison] = []
    for path in sorted(template_dir.glob("*.png")):
        candidate = path.name.split("-", 1)[0]
        template = Image.open(path).convert("L")
        comparisons.append(GlyphComparison(candidate, str(Path(args.style) / path.name), round(_score(observed, template), 6)))

    comparisons.sort(key=lambda item: item.score)
    summaries = _summaries(comparisons, args.top_k)
    best_class = summaries[0] if summaries else None
    second_class = summaries[1] if len(summaries) > 1 else None
    class_margin = None
    if best_class is not None and second_class is not None:
        class_margin = round(second_class.median_top_score - best_class.median_top_score, 6)

    lx, ly, lw, lh = local_bbox
    payload = {
        "word": args.word,
        "index": args.index,
        "style": args.style,
        "ocr_character": args.word[args.index] if 0 <= args.index < len(args.word) else None,
        "word_bbox": [x, y, w, h],
        "glyph_bbox_in_word": [lx, ly, lw, lh],
        "glyph_bbox_in_image": [x + lx, y + ly, lw, lh],
        "observed_crop": observed_path,
        "context_crop": context_path,
        "top_k": args.top_k,
        "best_candidate": asdict(best_class) if best_class else None,
        "class_margin": class_margin,
        "candidate_summaries": [asdict(item) for item in summaries],
        "nearest_templates": [asdict(item) for item in comparisons[:30]],
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
