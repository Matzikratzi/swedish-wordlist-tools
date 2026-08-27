from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image


def _black_pixels(path: Path, threshold: int) -> tuple[list[list[int]], int, int]:
    im = Image.open(path).convert("L")
    pts: list[list[int]] = []
    for y in range(im.height):
        for x in range(im.width):
            if im.getpixel((x, y)) < threshold:
                pts.append([x, y])
    return pts, im.width, im.height


def _safe(value: str) -> str:
    out = []
    for ch in value:
        if ch.isalnum() or ch in "-_åäöÅÄÖ":
            out.append(ch)
        else:
            out.append("_")
    return "".join(out).strip("_")[:80] or "word"


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Convert a saol-next-glyph-review-batch-v2 crop batch into strict word-debug JSON files."
    )
    ap.add_argument("batch", type=Path)
    ap.add_argument("library", type=Path, help="Word-image library containing the batch word_file paths")
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--threshold", type=int, default=210)
    args = ap.parse_args()

    payload = json.loads(args.batch.read_text(encoding="utf-8"))
    if payload.get("format") != "saol-next-glyph-review-batch-v2":
        raise SystemExit(f"unsupported batch format: {payload.get('format')!r}")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    for i, row in enumerate(payload.get("results") or []):
        rel = str(row.get("word_file") or "")
        image_path = args.library / rel
        if not image_path.exists():
            raise SystemExit(f"missing crop: {image_path}")
        black, width, height = _black_pixels(image_path, args.threshold)
        expected = str(row.get("expected_word") or row.get("headword") or "")
        page = row.get("page")
        subnr = row.get("subnr")
        debug = {
            "format": "saol14-word-debug-v1",
            "expected_word": expected,
            "headword": str(row.get("headword") or expected),
            "page": page,
            "subnr": subnr,
            "style": str(row.get("style") or "bold"),
            "width": width,
            "height": height,
            "black_pixels": black,
            "card_dataset": {
                "sourceId": str(row.get("source_id") or ""),
                "wordFile": rel,
                "style": str(row.get("style") or "bold"),
            },
        }
        name = f"saol14-word-debug-{i:02d}-p{page}-sub{subnr}-{_safe(expected)}.json"
        (args.out_dir / name).write_text(json.dumps(debug, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written += 1

    print(f"word_debug_files={written}")
    print(args.out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
