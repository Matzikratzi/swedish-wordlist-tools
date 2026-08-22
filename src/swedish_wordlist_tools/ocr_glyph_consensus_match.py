from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from PIL import Image, ImageChops

from .ocr_glyph_leave_one_out import _label
from .ocr_glyph_templates import _trim


def semantic_label(path: Path) -> str:
    """Return the actual glyph class encoded by the template filename.

    Keep punctuation/symbol classes distinct here. Any JSONL semantic mapping
    belongs above the visual classifier.
    """
    return _label(path)


def _ink(img: Image.Image) -> Image.Image:
    return ImageChops.invert(_trim(img.convert("L")))


def _x_profile(ink: Image.Image, threshold: int = 24) -> list[int]:
    px = ink.load()
    return [sum(1 for y in range(ink.height) if px[x, y] >= threshold) for x in range(ink.width)]


def _x_groups(profile: list[int], max_gap: int = 1) -> list[tuple[int, int, int]]:
    """Return (start, end, ink_count) horizontal ink groups."""
    active = [i for i, n in enumerate(profile) if n > 0]
    if not active:
        return []
    groups: list[tuple[int, int, int]] = []
    start = prev = active[0]
    for x in active[1:]:
        if x - prev > max_gap + 1:
            groups.append((start, prev + 1, sum(profile[start:prev + 1])))
            start = x
        prev = x
    groups.append((start, prev + 1, sum(profile[start:prev + 1])))
    return groups


def _horizontal_support(img: Image.Image, threshold: int = 24) -> Image.Image | None:
    """Keep one coherent horizontal glyph support; reject ambiguous neighbours.

    SAOL glyphs may have vertically disconnected components (i/ä/:), but those
    components still share one horizontal x-support.  Earlier char boxes can
    contain neighbour ink, especially disastrous for l and '.'.  We therefore
    split by x-support and retain the dominant group only when it clearly owns
    the crop.  Competing groups are rejected instead of poisoning consensus.
    """
    ink = _ink(img)
    if ink.width <= 0 or ink.height <= 0:
        return None
    profile = _x_profile(ink, threshold=threshold)
    groups = _x_groups(profile, max_gap=1)
    if not groups:
        return None
    ranked = sorted(groups, key=lambda g: (g[2], g[1] - g[0]), reverse=True)
    best = ranked[0]
    total = sum(g[2] for g in groups)
    if len(ranked) > 1:
        second = ranked[1]
        # If a second horizontal group carries substantial ink, this is likely
        # a multi-glyph crop. Reject rather than guessing which neighbour wins.
        if second[2] >= max(2, round(best[2] * 0.35)):
            return None
    x0, x1, _ = best
    cropped = ink.crop((x0, 0, x1, ink.height))
    binary = cropped.point(lambda p: 255 if p >= threshold else 0)
    bbox = binary.getbbox() or cropped.getbbox()
    if not bbox:
        return None
    return cropped.crop(bbox)


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
    """Return weights for glyph support: stable ink high, variable ink low."""
    w, h = median.size
    med = list(median.getdata())
    rows = [list(im.getdata()) for im in images]
    out = []
    for i in range(w * h):
        support = max([med[i], *(row[i] for row in rows)])
        if support <= 0:
            out.append(0)
            continue
        mad = sum(abs(row[i] - med[i]) for row in rows) / len(rows)
        stability = max(51, round(255 - min(204, mad * 2.2)))
        ink_weight = max(32, min(255, support))
        out.append(round(stability * ink_weight / 255))
    mask = Image.new("L", (w, h), 0)
    mask.putdata(out)
    return mask


def _geometry_from_ink(ink: Image.Image) -> dict[str, float]:
    bbox = ink.getbbox()
    if not bbox:
        return {"width": 0.0, "height": 0.0, "area": 0.0, "aspect": 0.0, "fill": 0.0}
    cropped = ink.crop(bbox)
    vals = list(cropped.getdata())
    area = sum(vals) / 255.0
    width = float(cropped.width)
    height = float(cropped.height)
    return {
        "width": width,
        "height": height,
        "area": round(area, 4),
        "aspect": round(height / width, 4) if width else 0.0,
        "fill": round(area / (width * height), 4) if width and height else 0.0,
    }


def _geometry(img: Image.Image) -> dict[str, float]:
    support = _horizontal_support(img)
    return _geometry_from_ink(support) if support is not None else {
        "width": 0.0, "height": 0.0, "area": 0.0, "aspect": 0.0, "fill": 0.0
    }


def _geometry_penalty(query: dict[str, float], model: dict[str, float]) -> float:
    """Small shape prior; enough to separate dot-like from tall-stem glyphs."""
    if not query["width"] or not query["height"] or not model["width"] or not model["height"]:
        return 0.0
    h = abs(query["height"] - model["height"]) / max(query["height"], model["height"])
    w = abs(query["width"] - model["width"]) / max(query["width"], model["width"])
    a = abs(query["aspect"] - model["aspect"]) / max(query["aspect"], model["aspect"], 1e-6)
    f = abs(query["fill"] - model["fill"])
    return 0.08 * h + 0.04 * w + 0.06 * a + 0.02 * f


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
        accepted: list[tuple[Path, Image.Image]] = []
        rejected: list[str] = []
        for path in paths:
            support = _horizontal_support(Image.open(path).convert("L"))
            if support is None:
                rejected.append(path.name)
            else:
                accepted.append((path, support))
        if not accepted:
            continue
        raw = [im for _path, im in accepted]
        anchor = _medoid(raw, max_shift)
        aligned = [_best_aligned(im, anchor, max_shift) for im in raw]
        median = _median(aligned)
        mask = _stability_mask(aligned, median)
        bbox = median.getbbox()
        if bbox:
            median = median.crop(bbox)
            mask = mask.crop(bbox)
        result[ch] = {
            "median": median,
            "mask": mask,
            "geometry": _geometry_from_ink(median),
            "count": len(raw),
            "templates": [p.name for p, _im in accepted],
            "rejected_templates": rejected,
        }
    return result


def _weighted_shift_score(query: Image.Image, median: Image.Image, mask: Image.Image, max_shift: int) -> tuple[float, int, int]:
    q = _horizontal_support(query)
    if q is None:
        return 2.0, 0, 0
    pad = max_shift + 3
    width = max(q.width, median.width) + 2 * pad
    height = max(q.height, median.height) + 2 * pad
    med = _canvas(median, width, height, pad, pad)
    msk = _canvas(mask, width, height, pad, pad)
    medvals = list(med.getdata())
    weights = list(msk.getdata())
    denom = sum(weights) or 1
    best = (2.0, 0, 0)
    for dy in range(-max_shift, max_shift + 1):
        for dx in range(-max_shift, max_shift + 1):
            qq = _canvas(q, width, height, pad + dx, pad + dy)
            qvals = list(qq.getdata())
            score = sum(abs(a - b) * w for a, b, w in zip(qvals, medvals, weights)) / (255.0 * denom)
            if score < best[0]:
                best = (score, dx, dy)
    return best


def classify_consensus(query: Image.Image, refs: list[Path], max_shift: int = 3) -> dict[str, object]:
    models = build_consensus(refs, max_shift=max_shift)
    query_geometry = _geometry(query)
    ranked = []
    for ch, model in models.items():
        pixel_score, dx, dy = _weighted_shift_score(query, model["median"], model["mask"], max_shift)
        geometry_penalty = _geometry_penalty(query_geometry, model["geometry"])
        singleton_penalty = 0.01 if int(model["count"]) == 1 else 0.0
        score = pixel_score + geometry_penalty + singleton_penalty
        ranked.append({
            "character": ch,
            "score": round(score, 6),
            "pixel_score": round(pixel_score, 6),
            "geometry_penalty": round(geometry_penalty, 6),
            "singleton_penalty": singleton_penalty,
            "dx": dx,
            "dy": dy,
            "reference_count": model["count"],
            "rejected_reference_count": len(model.get("rejected_templates", [])),
            "model_geometry": model["geometry"],
        })
    ranked.sort(key=lambda row: float(row["score"]))
    best = ranked[0] if ranked else None
    second = ranked[1] if len(ranked) > 1 else None
    margin = None
    if best is not None and second is not None:
        margin = round(float(second["score"]) - float(best["score"]), 6)
    return {
        "best": best,
        "second": second,
        "margin": margin,
        "ranked": ranked,
        "query_geometry": query_geometry,
    }
