from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageChops

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


def _segment_word(img: Image.Image, expected_chars: int | None = None) -> list[tuple[int, int, Image.Image]]:
    """Segment a word crop into horizontal glyph candidates without OCR labels.

    The first pass uses x-ink groups. If the number of groups is smaller than an
    expected character count, recursively split the widest groups at their
    deepest internal x-profile valleys. This is deliberately conservative and
    intended for SAOL's stable typography, not arbitrary OCR.
    """
    gray = _trim(img.convert("L"))
    profile = _ink_columns(gray)
    groups = _x_groups(profile, max_gap=1)

    if expected_chars and expected_chars > 0:
        while len(groups) < expected_chars:
            best = None
            for gi, (a, b) in enumerate(groups):
                if b - a < 4:
                    continue
                local = profile[a:b]
                lo = 1
                hi = len(local) - 1
                if hi <= lo:
                    continue
                # Prefer an empty column; otherwise the least-ink internal valley.
                rel = min(range(lo, hi), key=lambda i: (local[i], abs(i - len(local)/2)))
                score = local[rel]
                width = b - a
                candidate = (score, -width, gi, a + rel)
                if best is None or candidate < best:
                    best = candidate
            if best is None:
                break
            _score, _negwidth, gi, cut = best
            a, b = groups[gi]
            if cut <= a or cut >= b:
                break
            groups = groups[:gi] + [(a, cut), (cut, b)] + groups[gi+1:]

    out: list[tuple[int, int, Image.Image]] = []
    for a, b in groups:
        glyph = _trim(gray.crop((a, 0, b, gray.height)))
        if glyph.width > 0 and glyph.height > 0:
            out.append((a, b, glyph))
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
    segments = _segment_word(img, expected_chars)

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
            "segmentation": "horizontal ink groups; widest groups split at internal valleys when expected length is supplied",
        },
    }
    json.dump(payload, __import__("sys").stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
