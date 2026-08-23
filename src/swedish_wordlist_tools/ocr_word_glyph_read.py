from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image

from .ocr_glyph_classify import classify_glyph
from .ocr_glyph_templates import _trim


def _ink_columns(img: Image.Image, threshold: int = 220) -> list[int]:
    gray = img.convert("L")
    px = gray.load()
    return [sum(1 for y in range(gray.height) if px[x, y] < threshold) for x in range(gray.width)]


def _x_groups(profile: list[int], max_gap: int = 1) -> list[tuple[int, int]]:
    active = [i for i, n in enumerate(profile) if n > 0]
    if not active:
        return []
    groups: list[tuple[int, int]] = []
    start = prev = active[0]
    for x in active[1:]:
        if x - prev > max_gap + 1:
            groups.append((start, prev + 1))
            start = x
        prev = x
    groups.append((start, prev + 1))
    return groups


def _darkness(value: int) -> float:
    return max(0.0, min(1.0, (255.0 - float(value)) / 255.0))


def _boundary_cost(gray: Image.Image, x: int, y: int) -> float:
    """Cost of putting a zero-width boundary between pixels x-1 and x.

    A seam may hug an ink edge, so one dark adjacent pixel is acceptable. Two
    dark pixels on opposite sides are expensive because that is evidence that
    the boundary would cut a connected stroke rather than pass through the
    background between two printed glyphs.
    """
    px = gray.load()
    left = _darkness(px[x - 1, y])
    right = _darkness(px[x, y])
    return 2.8 * min(left, right) + 0.35 * max(left, right)


def _best_background_seam(gray: Image.Image) -> tuple[float, list[int]] | None:
    """Find a top-to-bottom zero-width background seam with dynamic programming.

    The seam lives *between* pixel columns, not on a column. From one row to the
    next it may stay put or move one pixel left/right. This lets it wind around
    serifs and italic strokes while strongly disfavoring paths that cut ink.
    """
    gray = gray.convert("L")
    width, height = gray.size
    if width < 3 or height < 1:
        return None

    xs = range(1, width)
    inf = 1e18
    prev = {x: _boundary_cost(gray, x, 0) for x in xs}
    parents: list[dict[int, int]] = []

    for y in range(1, height):
        cur: dict[int, float] = {}
        parent: dict[int, int] = {}
        for x in xs:
            best_cost = inf
            best_prev = x
            for xp in (x - 1, x, x + 1):
                if xp not in prev:
                    continue
                # Small movement penalty: bending is allowed, zig-zagging is not free.
                cost = prev[xp] + 0.055 * abs(x - xp)
                if cost < best_cost:
                    best_cost = cost
                    best_prev = xp
            cur[x] = best_cost + _boundary_cost(gray, x, y)
            parent[x] = best_prev
        parents.append(parent)
        prev = cur

    # Avoid the trivial outside-edge path. The penalty is deliberately weak:
    # typography evidence should dominate, but a genuine inter-glyph seam is
    # expected to leave ink on both sides.
    center = width / 2.0
    def terminal_score(x: int) -> float:
        edge = min(x, width - x)
        edge_penalty = 0.8 / max(1.0, float(edge))
        center_penalty = 0.015 * abs(x - center) / max(1.0, width)
        return prev[x] + edge_penalty + center_penalty

    end_x = min(xs, key=terminal_score)
    score = terminal_score(end_x)
    path = [end_x]
    x = end_x
    for parent in reversed(parents):
        x = parent[x]
        path.append(x)
    path.reverse()
    return score, path


def _split_by_seam(gray: Image.Image, seam: list[int]) -> tuple[Image.Image, Image.Image]:
    """Split an image along a zero-width row-wise seam."""
    gray = gray.convert("L")
    left = gray.copy()
    right = gray.copy()
    lp = left.load()
    rp = right.load()
    width, height = gray.size
    for y in range(height):
        cut = max(1, min(width - 1, seam[y]))
        for x in range(width):
            if x >= cut:
                lp[x, y] = 255
            if x < cut:
                rp[x, y] = 255
    return _trim(left), _trim(right)


def _split_candidate(group_image: Image.Image) -> tuple[float, Image.Image, Image.Image] | None:
    """Return the best usable seam split for one connected group."""
    gray = group_image.convert("L")
    found = _best_background_seam(gray)
    if found is None:
        return None
    score, seam = found
    left, right = _split_by_seam(gray, seam)
    if left.width <= 0 or right.width <= 0 or left.height <= 0 or right.height <= 0:
        return None

    # Penalize implausibly tiny pieces and gross imbalance, but do not impose a
    # letter-pair-specific rule. The seam geometry remains the main evidence.
    total_w = max(1, left.width + right.width)
    tiny_penalty = 0.0
    if min(left.width, right.width) <= 1:
        tiny_penalty += 1.0
    balance_penalty = 0.06 * abs(left.width - right.width) / total_w
    return score + tiny_penalty + balance_penalty, left, right


def _segment_word(
    img: Image.Image,
    expected_chars: int | None = None,
    *,
    style: str | None = None,
    expected_text: str | None = None,
) -> list[tuple[int, int, Image.Image]]:
    """Segment a SAOL word crop into glyph candidates without OCR labels.

    Disconnected x-ink groups are preserved. If fewer groups exist than the
    known character count, connected groups are recursively split by a
    top-to-bottom *zero-width background seam*. The seam may move one pixel
    sideways per row, so overlapping serifs and forward-leaning italic strokes
    do not require a completely white vertical column between glyphs.

    ``style`` and ``expected_text`` are accepted for API compatibility and future
    priors; the actual cut geometry is currently style- and pair-independent.
    """
    gray = _trim(img.convert("L"))
    profile = _ink_columns(gray)
    groups: list[dict[str, object]] = [
        {"a": a, "b": b, "image": _trim(gray.crop((a, 0, b, gray.height)))}
        for a, b in _x_groups(profile, max_gap=1)
    ]

    if expected_chars and expected_chars > 0:
        while len(groups) < expected_chars:
            best: tuple[float, float, int, Image.Image, Image.Image] | None = None
            for gi, group in enumerate(groups):
                glyph = group.get("image")
                if not isinstance(glyph, Image.Image) or glyph.width < 3:
                    continue
                split = _split_candidate(glyph)
                if split is None:
                    continue
                score, left, right = split
                # Prefer resolving wide connected groups when seam evidence ties.
                candidate = (score, -float(glyph.width), gi, left, right)
                if best is None or candidate[:3] < best[:3]:
                    best = candidate
            if best is None:
                break

            _score, _negwidth, gi, left, right = best
            group = groups[gi]
            a, b = int(group["a"]), int(group["b"])
            # x ranges are only diagnostics now: the actual boundary can vary by
            # row. Use the trimmed-width proportion as a stable approximate split.
            denom = max(1, left.width + right.width)
            approx = a + max(1, min(b - a - 1, round((b - a) * left.width / denom)))
            groups = groups[:gi] + [
                {"a": a, "b": approx, "image": left},
                {"a": approx, "b": b, "image": right},
            ] + groups[gi + 1:]

    out: list[tuple[int, int, Image.Image]] = []
    for group in groups:
        glyph = group["image"]
        if isinstance(glyph, Image.Image) and glyph.width > 0 and glyph.height > 0:
            out.append((int(group["a"]), int(group["b"]), glyph))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Read one SAOL word crop glyph-by-glyph without OCR character labels.")
    ap.add_argument("word_crop", type=Path)
    ap.add_argument("templates", type=Path)
    ap.add_argument("--style", choices=("italic", "bold", "roman"), required=True)
    ap.add_argument("--expected", help="Known text used only for evaluation/expected character count; + is treated as printed ~")
    ap.add_argument("--max-shift", type=int, default=3)
    ap.add_argument("--margin", type=float, default=0.02)
    ap.add_argument("--segments-out", type=Path)
    args = ap.parse_args()

    img = Image.open(args.word_crop).convert("L")
    expected = args.expected.replace("+", "~") if args.expected is not None else None
    expected_chars = len(expected) if expected is not None else None
    segments = _segment_word(img, expected_chars, style=args.style, expected_text=expected)

    if args.segments_out:
        args.segments_out.mkdir(parents=True, exist_ok=True)

    rows = []
    chars = []
    for i, (x0, x1, glyph) in enumerate(segments):
        if args.segments_out:
            glyph.save(args.segments_out / f"glyph-{i:02d}.png")
        result = classify_glyph(
            glyph,
            args.templates,
            args.style,
            max_shift=args.max_shift,
            top=5,
            require_margin=args.margin,
        )
        pred = result.get("prediction")
        chars.append(str(pred) if pred is not None else "?")
        rows.append({
            "index": i,
            "x": [x0, x1],
            "prediction": pred,
            "status": result.get("status"),
            "best": result.get("best"),
            "second_class": result.get("second_class"),
            "margin": result.get("margin"),
        })

    text = "".join(chars)
    payload = {
        "word_crop": str(args.word_crop),
        "style": args.style,
        "segment_count": len(segments),
        "prediction": text,
        "expected": expected,
        "correct": (text == expected) if expected is not None else None,
        "margin_threshold": args.margin,
        "segments": rows,
        "notes": {
            "character_labels": "not taken from Tesseract",
            "segmentation": "ink groups; connected glyphs split by zero-width dynamic background seams",
        },
    }
    json.dump(payload, __import__("sys").stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
