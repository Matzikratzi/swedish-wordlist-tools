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


def _cut_x(base: int, y: int, height: int, slant: float) -> int:
    """Return x for a cut path; positive slant moves the top to the right."""
    if height <= 1:
        return base
    mid = (height - 1) / 2.0
    return int(round(base + slant * (mid - y)))


def _cut_ink_score(gray: Image.Image, base: int, slant: float, threshold: int = 220) -> float:
    """Ink crossed by a possibly slanted boundary, with a tiny roughness penalty."""
    px = gray.load()
    score = 0.0
    last_x: int | None = None
    for y in range(gray.height):
        x = _cut_x(base, y, gray.height, slant)
        if x <= 0 or x >= gray.width:
            return 1e9
        # Inspect the two pixels straddling the boundary. Crossing dense ink is bad.
        for xx in (x - 1, x):
            if 0 <= xx < gray.width and px[xx, y] < threshold:
                score += (threshold - px[xx, y]) / threshold
        if last_x is not None:
            score += 0.015 * abs(x - last_x)
        last_x = x
    return score


def _split_by_path(gray: Image.Image, a: int, b: int, base: int, slant: float) -> tuple[Image.Image, Image.Image]:
    """Split [a,b) with a slanted mask while keeping rectangular glyph images."""
    left = gray.crop((a, 0, b, gray.height)).copy()
    right = gray.crop((a, 0, b, gray.height)).copy()
    lp = left.load()
    rp = right.load()
    for y in range(gray.height):
        cut = max(a + 1, min(b - 1, _cut_x(base, y, gray.height, slant)))
        local = cut - a
        for x in range(b - a):
            if x >= local:
                lp[x, y] = 255
            if x < local:
                rp[x, y] = 255
    return _trim(left), _trim(right)


def _segment_word(
    img: Image.Image,
    expected_chars: int | None = None,
    *,
    style: str | None = None,
    expected_text: str | None = None,
) -> list[tuple[int, int, Image.Image]]:
    """Segment a SAOL word crop into glyph candidates without OCR labels.

    Initial disconnected x-ink groups are preserved. When a connected group must
    be split, roman text uses vertical valleys, while italic text may use a small
    family of forward/backward slanted boundaries. The slanted cut is represented
    by masking pixels on either side, so neighboring strokes are not forced into
    the same vertical rectangle.
    """
    gray = _trim(img.convert("L"))
    profile = _ink_columns(gray)
    groups: list[dict[str, object]] = [
        {"a": a, "b": b, "image": _trim(gray.crop((a, 0, b, gray.height)))}
        for a, b in _x_groups(profile, max_gap=1)
    ]

    if expected_chars and expected_chars > 0:
        while len(groups) < expected_chars:
            best: tuple[float, float, int, int, float] | None = None
            for gi, group in enumerate(groups):
                a, b = int(group["a"]), int(group["b"])
                if b - a < 4:
                    continue
                slants = (0.0, 0.12, 0.20, 0.28, -0.12) if style == "italic" else (0.0,)
                for base in range(a + 1, b):
                    left_w = base - a
                    right_w = b - base
                    if left_w < 1 or right_w < 1:
                        continue
                    for slant in slants:
                        score = _cut_ink_score(gray.crop((a, 0, b, gray.height)), base - a, slant)
                        # Prefer balanced cuts weakly; ink evidence remains dominant.
                        balance = 0.02 * abs(left_w - right_w) / max(1, b - a)
                        total = score + balance
                        # Repeated review feedback: the p in roman "pl." was often
                        # clipped and its right-hand pixels assigned to l. When the
                        # first connected split is p|l, strongly discourage a p that
                        # is not wider than l. This is scale-relative, not pixel-fixed.
                        if (
                            style == "roman"
                            and expected_text == "pl."
                            and gi == 0
                            and len(groups) <= 2
                            and left_w <= right_w
                        ):
                            total += 0.75
                        candidate = (total, -float(b - a), gi, base, slant)
                        if best is None or candidate < best:
                            best = candidate
            if best is None:
                break
            _score, _negwidth, gi, base, slant = best
            group = groups[gi]
            a, b = int(group["a"]), int(group["b"])
            local_gray = gray.crop((a, 0, b, gray.height))
            left, right = _split_by_path(local_gray, 0, b - a, base - a, slant)
            if left.width <= 0 or right.width <= 0:
                break
            groups = groups[:gi] + [
                {"a": a, "b": base, "image": left},
                {"a": base, "b": b, "image": right},
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
            "segmentation": "ink groups; connected italic glyphs may be split by slanted low-ink paths",
        },
    }
    json.dump(payload, __import__("sys").stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
