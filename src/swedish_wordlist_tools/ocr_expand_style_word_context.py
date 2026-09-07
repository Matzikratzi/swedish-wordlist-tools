from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from pathlib import Path

from PIL import Image

from .ocr_mine_jsonl_pages import _crop_columns, _download, _source_for_page


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Rebuild style-word crops from facsimile columns with real context above/beside the OCR word box."
    )
    ap.add_argument("library", type=Path, help="Existing style-word library")
    ap.add_argument("jsonl", type=Path, help="SAOL facsimile JSONL used to resolve page images")
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--above", type=int, default=8, help="Real source pixels to include above OCR bbox")
    ap.add_argument("--side", type=int, default=2, help="Real source pixels to include left/right")
    ap.add_argument("--below", type=int, default=2, help="Real source pixels to include below OCR bbox")
    args = ap.parse_args()

    manifest_path = args.library / "manifest-style-word-segments.json"
    if not manifest_path.exists():
        raise SystemExit(f"missing {manifest_path}")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    words = payload.get("words", [])
    if not isinstance(words, list):
        raise SystemExit("manifest words is not a list")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    word_dir = args.out_dir / "words"
    word_dir.mkdir(parents=True, exist_ok=True)

    # Preserve any non-word assets/metadata that callers may expect, but rebuild
    # words and manifest below.  Avoid copying the potentially large words tree.
    for child in args.library.iterdir():
        if child.name in {"words", "manifest-style-word-segments.json"}:
            continue
        dest = args.out_dir / child.name
        if dest.exists():
            continue
        if child.is_dir():
            shutil.copytree(child, dest)
        else:
            shutil.copy2(child, dest)

    cache: dict[tuple[int, int], tuple[Image.Image, int]] = {}
    owned = tempfile.TemporaryDirectory(prefix="saol-context-pages-")
    root = Path(owned.name)

    rebuilt: list[dict[str, object]] = []
    for idx, raw in enumerate(words):
        if not isinstance(raw, dict):
            continue
        word = dict(raw)
        page = int(word.get("page") or 0)
        colno = int(word.get("column") or 0)
        bbox = word.get("word_bbox")
        if not page or not colno or not isinstance(bbox, list) or len(bbox) != 4:
            continue
        left, top, width, height = map(int, bbox)

        key = (page, colno)
        cached = cache.get(key)
        if cached is None:
            source = _source_for_page(args.jsonl, page)
            if not source:
                raise SystemExit(f"no facsimile source for page {page}")
            page_dir = root / f"page-{page:05d}"
            page_dir.mkdir(parents=True, exist_ok=True)
            image_path = page_dir / Path(source).name
            if not image_path.exists():
                _download(source, image_path)
            columns = _crop_columns(image_path, page_dir)
            if colno < 1 or colno > len(columns):
                raise SystemExit(f"page {page}: missing column {colno}")
            column_path, column_left = columns[colno - 1]
            cached = (Image.open(column_path).convert("L"), int(column_left))
            cache[key] = cached
        column_img, column_left = cached

        x0 = max(0, left - args.side)
        y0 = max(0, top - args.above)
        x1 = min(column_img.width, left + width + args.side)
        y1 = min(column_img.height, top + height + args.below)
        crop = column_img.crop((x0, y0, x1, y1))

        old_rel = str(word.get("word_file") or "")
        old_name = Path(old_rel).name if old_rel else f"w{idx:05d}.png"
        out_file = word_dir / old_name
        crop.save(out_file)

        dx = left - x0
        dy = top - y0
        word["word_file"] = str(out_file.relative_to(args.out_dir))
        word["original_word_bbox"] = [left, top, width, height]
        word["word_bbox"] = [x0, y0, x1 - x0, y1 - y0]
        word["context_offset"] = [dx, dy]
        word["original_word_size"] = [width, height]
        word["column_left"] = column_left
        word["context_above"] = dy
        word["context_side_left"] = dx
        rebuilt.append(word)

    payload["words"] = rebuilt
    payload["word_count"] = len(rebuilt)
    notes = payload.setdefault("notes", {})
    if isinstance(notes, dict):
        notes["context_crops"] = (
            f"word_file rebuilt from original facsimile column with up to {args.above}px above, "
            f"{args.side}px each side and {args.below}px below OCR bbox"
        )
    (args.out_dir / "manifest-style-word-segments.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(args.out_dir)
    print(f"words={len(rebuilt)} above={args.above} side={args.side} below={args.below}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
