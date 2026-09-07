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


def _ink_mask(gray: Image.Image, threshold: int = 220) -> list[list[bool]]:
    gray = gray.convert("L")
    px = gray.load()
    return [[px[x, y] < threshold for x in range(gray.width)] for y in range(gray.height)]


def _ink_at(mask: list[list[bool]], x: int, y: int) -> bool:
    if not mask:
        return False
    height = len(mask)
    width = len(mask[0])
    return 0 <= x < width and 0 <= y < height and mask[y][x]


def _vertex_open(mask: list[list[bool]], x: int, y: int) -> bool:
    """Whether a dual-grid vertex is a genuine background passage.

    A path must not squeeze through a corner where two ink pixels touch
    diagonally. Treating such diagonal contact as connected is exactly the
    topology we want for printed glyphs: different letters are assumed to have
    air between them even on the diagonal.
    """
    nw = _ink_at(mask, x - 1, y - 1)
    ne = _ink_at(mask, x, y - 1)
    sw = _ink_at(mask, x - 1, y)
    se = _ink_at(mask, x, y)
    return not ((nw and se) or (ne and sw))


def _vertical_edge_open(mask: list[list[bool]], x: int, y: int) -> bool:
    """Can a zero-width seam run vertically between columns x-1 and x?"""
    return not (_ink_at(mask, x - 1, y) and _ink_at(mask, x, y))


def _horizontal_edge_open(mask: list[list[bool]], column: int, y: int) -> bool:
    """Can the seam shift sideways across the row boundary at y?"""
    return not (_ink_at(mask, column, y - 1) and _ink_at(mask, column, y))


def _edge_hug_penalty(mask: list[list[bool]], x: int, y: int) -> float:
    """Weakly prefer open air, while allowing a seam to hug a serif edge."""
    touches = int(_ink_at(mask, x - 1, y)) + int(_ink_at(mask, x, y))
    return 0.035 * touches


def _best_topological_seam(gray: Image.Image, threshold: int = 220) -> tuple[float, list[int]] | None:
    """Find a strict top-to-bottom separator through the background topology.

    The seam lives on the *boundaries between pixels*, so it has zero thickness.
    It may stay in the same x position or move one pixel left/right at each row.
    A move is forbidden if it would cross horizontal/vertical ink connectivity,
    and a vertex is forbidden if it would squeeze between diagonally touching ink
    pixels. Thus the seam can snake around overlapping serifs without ever
    cutting an 8-connected ink component.
    """
    gray = gray.convert("L")
    width, height = gray.size
    if width < 3 or height < 1:
        return None

    mask = _ink_mask(gray, threshold=threshold)
    xs = range(1, width)
    center = width / 2.0
    inf = 1e18

    prev: dict[int, float] = {}
    for x in xs:
        if _vertex_open(mask, x, 0):
            prev[x] = 0.002 * abs(x - center)
    if not prev:
        return None

    parents: list[dict[int, int]] = []
    for y in range(height):
        cur: dict[int, float] = {}
        parent: dict[int, int] = {}
        for xp, prev_cost in prev.items():
            for x in (xp - 1, xp, xp + 1):
                if x <= 0 or x >= width:
                    continue
                if not _vertex_open(mask, x, y):
                    continue
                if x != xp:
                    column = min(x, xp)
                    if not _horizontal_edge_open(mask, column, y):
                        continue
                if not _vertical_edge_open(mask, x, y):
                    continue
                if not _vertex_open(mask, x, y + 1):
                    continue

                cost = prev_cost
                cost += 0.02 * abs(x - xp)
                cost += _edge_hug_penalty(mask, x, y)
                cost += 0.002 * abs(x - center) / max(1.0, width)
                if cost < cur.get(x, inf):
                    cur[x] = cost
                    parent[x] = xp
        if not cur:
            return None
        parents.append(parent)
        prev = cur

    end_x = min(prev, key=lambda x: (prev[x], abs(x - center)))
    score = prev[end_x]

    vertices = [end_x]
    x = end_x
    for parent in reversed(parents):
        x = parent[x]
        vertices.append(x)
    vertices.reverse()

    # The vertical segment crossing image row y uses the boundary after any
    # sideways move at that row, i.e. vertex y+1.
    seam = vertices[1:]
    if len(seam) != height:
        return None
    return score, seam


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
    """Return the best strict topological split for one x-connected group."""
    gray = group_image.convert("L")
    found = _best_topological_seam(gray)
    if found is None:
        return None
    score, seam = found
    left, right = _split_by_seam(gray, seam)
    if left.width <= 0 or right.width <= 0 or left.height <= 0 or right.height <= 0:
        return None

    # Reject near-empty slivers; otherwise keep priors deliberately weak. The
    # separator itself is already guaranteed not to cut an 8-connected stroke.
    if min(left.width, right.width) <= 1:
        score += 0.8
    total_w = max(1, left.width + right.width)
    score += 0.035 * abs(left.width - right.width) / total_w
    return score, left, right


def _segment_word(
    img: Image.Image,
    expected_chars: int | None = None,
    *,
    style: str | None = None,
    expected_text: str | None = None,
) -> list[tuple[int, int, Image.Image]]:
    """Segment a SAOL word crop into glyph candidates without OCR labels.

    Easy gaps are separated first by x projection. If the known character count
    says that an x-connected region still contains multiple glyphs, it is split
    only where a strict zero-width topological background seam exists. Such a
    seam may wind around serifs and italic strokes, but it is forbidden to cut
    horizontal, vertical, or diagonal ink connectivity.

    ``style`` and ``expected_text`` are accepted for API compatibility; the
    geometry itself is intentionally style- and character-pair-independent.
    """
    gray = _trim(img.convert("L"))
    profile = _ink_columns(gray)
    groups: list[dict[str, object]] = [
        {"a": a, "b": b, "image": _trim(gray.crop((a, 0, b, gray.height)))}
        for a, b in _x_groups(profile, max_gap=1)
    ]

    if expected_chars and expected_chars > 0:
        while len(groups) < expected_chars:
            best_key: tuple[float, float, int] | None = None
            best_value: tuple[int, Image.Image, Image.Image] | None = None
            for gi, group in enumerate(groups):
                glyph = group.get("image")
                if not isinstance(glyph, Image.Image) or glyph.width < 3:
                    continue
                split = _split_candidate(glyph)
                if split is None:
                    continue
                score, left, right = split
                key = (score, -float(glyph.width), gi)
                if best_key is None or key < best_key:
                    best_key = key
                    best_value = (gi, left, right)
            if best_value is None:
                break

            gi, left, right = best_value
            group = groups[gi]
            a, b = int(group["a"]), int(group["b"])
            # x ranges are diagnostic only because a topological seam can vary by
            # row. Use the trimmed-width proportion as an approximate scalar cut.
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
            "segmentation": "x gaps plus strict zero-width topological seams that cannot cut 8-connected ink",
        },
    }
    json.dump(payload, __import__("sys").stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
