from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from PIL import Image, ImageChops

from .ocr_glyph_leave_one_out import _label
from .ocr_glyph_templates import _trim


def semantic_label(path: Path) -> str:
    ch = _label(path)
    return "+" if ch in {"+", "~"} else ch


def _ink(img: Image.Image) -> Image.Image:
    return ImageChops.invert(_trim(img.convert("L")))


def _canvas(img: Image.Image, width: int, height: int, x: int, y: int) -> Image.Image:
    out = Image.new("L", (width, height), 0)
    out.paste(img, (x, y))
    return out


def _plain_score(a: Image.Image, b: Image.Image) -> float:
    vals = list(ImageChops.difference(a, b).getdata())
    return sum(vals) / (255.0 * len(vals)) if vals else 1.0


def _best_aligned(img: Image.Image, anchor: Image.Image, max_shift: int) -> Image.Image:
    pad = max_shift + 3
    width = max(img.width, anchor.width) + 2 * pad
    height = max(img.height, anchor.height) + 2 * pad
    aa = _canvas(anchor, width, height, pad, pad)
    best_score = 2.0
    best = None
    for dy in range(-max_shift, max_shift + 1):
        for dx in range(-max_shift, max_shift + 1):
            bb = _canvas(img, width, height, pad + dx, pad + dy)
            score = _plain_score(aa, bb)
            if score < best_score:
                best_score = score
                best = bb
    assert best is not None
    return best


def _median(images: list[Image.Image]) -> Image.Image:
    w, h = images[0].size
    rows = [list(im.getdata()) for im in images]
    out = []
    for i in range(w * h):
        vals = sorted(row[i] for row in rows)
        out.append(vals[len(vals) // 2])
    img = Image.new("L", (w, h), 0)
    img.putdata(out)
    return img


def _stability_mask(images: list[Image.Image], median: Image.Image) -> Image.Image:
    """Return weights: 255 stable, 51 highly variable."""
    w, h = median.size
    med = list(median.getdata())
    rows = [list(im.getdata()) for im in images]
    out = []
    for i in range(w * h):
        mad = sum(abs(row[i] - med[i]) for row in rows) / len(rows)
        out.append(max(51, round(255 - min(204, mad * 2.2))))
    mask = Image.new("L", (w, h), 255)
    mask.putdata(out)
    return mask


def _medoid(images: list[Image.Image], max_shift: int) -> Image.Image:
    if len(images) == 1:
        return images[0]
    totals = []
    for i, candidate in enumerate(images):
        total = 0.0
        for j, other in enumerate(images):
            if i == j:
                continue
            aligned = _best_aligned(other, candidate, max_shift)
            pad = max_shift + 3
            width = max(candidate.width, other.width) + 2 * pad
            height = max(candidate.height, other.height) + 2 * pad
            cc = _canvas(candidate, width, height, pad, pad)
            total += _plain_score(cc, aligned)
        totals.append((total, i))
    return images[min(totals)[1]]


def build_consensus(refs: list[Path], max_shift: int = 3) -> dict[str, dict[str, object]]:
    grouped: dict[str, list[Path]] = defaultdict(list)
    for path in refs:
        grouped[semantic_label(path)].append(path)
    result: dict[str, dict[str, object]] = {}
    for ch, paths in grouped.items():
        raw = [_ink(Image.open(p).convert("L")) for p in paths]
        anchor = _medoid(raw, max_shift)
        aligned = [_best_aligned(im, anchor, max_shift) for im in raw]
        median = _median(aligned)
        mask = _stability_mask(aligned, median)
        result[ch] = {
            "median": median,
            "mask": mask,
            "count": len(paths),
            "templates": [p.name for p in paths],
        }
    return result


def _weighted_shift_score(query: Image.Image, median: Image.Image, mask: Image.Image, max_shift: int) -> tuple[float, int, int]:
    q = _ink(query)
    pad = max_shift + 3
    width = max(q.width, median.width) + 2 * pad
    height = max(q.height, median.height) + 2 * pad
    med = _canvas(median, width, height, pad, pad)
    msk = _canvas(mask, width, height, pad, pad)
    medvals = list(med.getdata())
    weights = list(msk.getdata())
    best = (2.0, 0, 0)
    for dy in range(-max_shift, max_shift + 1):
        for dx in range(-max_shift, max_shift + 1):
            qq = _canvas(q, width, height, pad + dx, pad + dy)
            qvals = list(qq.getdata())
            denom = sum(weights) or 1
            score = sum(abs(a - b) * w for a, b, w in zip(qvals, medvals, weights)) / (255.0 * denom)
            if score < best[0]:
                best = (score, dx, dy)
    return best


def classify_consensus(query: Image.Image, refs: list[Path], max_shift: int = 3) -> dict[str, object]:
    models = build_consensus(refs, max_shift=max_shift)
    ranked = []
    for ch, model in models.items():
        score, dx, dy = _weighted_shift_score(query, model["median"], model["mask"], max_shift)
        ranked.append({
            "character": ch,
            "score": round(score, 6),
            "dx": dx,
            "dy": dy,
            "reference_count": model["count"],
        })
    ranked.sort(key=lambda row: float(row["score"]))
    best = ranked[0] if ranked else None
    second = ranked[1] if len(ranked) > 1 else None
    margin = None
    if best is not None and second is not None:
        margin = round(float(second["score"]) - float(best["score"]), 6)
    return {"best": best, "second": second, "margin": margin, "ranked": ranked}
