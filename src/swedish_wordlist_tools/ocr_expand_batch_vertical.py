from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image

from . import ocr_prepare_next20_glyph_words as prep


def _style_extents(facit_path: Path) -> dict[str, tuple[int, int]]:
    """Return maximum pixels above/below baseline for each learned style."""
    payload = json.loads(facit_path.read_text(encoding="utf-8"))
    ext: dict[str, tuple[int, int]] = {}
    for row in payload.get("glyphs") or []:
        if not isinstance(row, dict):
            continue
        style = str(row.get("style") or "roman")
        pts = row.get("pixels_relative_to_baseline") or []
        ys = [int(p[1]) for p in pts if isinstance(p, list) and len(p) == 2]
        if not ys:
            continue
        above = max(0, -min(ys))
        below = max(0, max(ys))
        old_above, old_below = ext.get(style, (0, 0))
        ext[style] = (max(old_above, above), max(old_below, below))
    return ext


def _manifest_lookup(manifest: dict[str, object]) -> dict[tuple[str, str, str], dict[str, object]]:
    out: dict[tuple[str, str, str], dict[str, object]] = {}
    for meta in (manifest.get("template_sources") or {}).values():
        if not isinstance(meta, dict):
            continue
        word = str(meta.get("expected_word") or meta.get("source_word") or "")
        key = (str(meta.get("page") or ""), str(meta.get("subnr") or ""), word)
        if word and key not in out:
            out[key] = meta
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Re-crop a glyph-review batch vertically using learned per-style baseline extents."
    )
    ap.add_argument("batch", type=Path)
    ap.add_argument("manifest", type=Path)
    ap.add_argument("library", type=Path)
    ap.add_argument("--facit", type=Path, required=True)
    ap.add_argument("--safety", type=int, default=2)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    batch = json.loads(args.batch.read_text(encoding="utf-8"))
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    lookup = _manifest_lookup(manifest)
    extents = _style_extents(args.facit)
    if not extents:
        raise SystemExit("no vertical extents found in facit")

    global_above = max(v[0] for v in extents.values())
    global_below = max(v[1] for v in extents.values())
    safety = max(0, args.safety)
    page_cache: dict[str, Image.Image] = {}
    changed = 0

    for row in batch.get("results") or []:
        if not isinstance(row, dict):
            continue
        word = str(row.get("expected_word") or row.get("headword") or "")
        key = (str(row.get("page") or ""), str(row.get("subnr") or ""), word)
        meta = lookup.get(key)
        if meta is None:
            continue
        bbox = meta.get("page_word_bbox")
        if not isinstance(bbox, list) or len(bbox) != 4:
            continue

        page_key = str(meta.get("page_image") or meta.get("source") or meta.get("page") or "")
        image = page_cache.get(page_key)
        if image is None:
            image = prep._load_page_image(meta)
            if image is None:
                continue
            page_cache[page_key] = image

        x, y, w, h = [int(v) for v in bbox]
        x = max(0, x)
        y = max(0, y)
        w = max(1, min(w, image.width - x))
        h = max(1, min(h, image.height - y))

        # Estimate the support baseline from the original crop.  This is only
        # geometry for re-cropping; it does not accept any OCR labels.
        original = image.crop((x, y, x + w, y + h))
        _matches, baseline0 = prep._match_models(original, prep._models(json.loads(Path(batch.get("source_atlas") or "").read_text(encoding="utf-8"))) if batch.get("source_atlas") and Path(str(batch.get("source_atlas"))).exists() else [])
        if not isinstance(baseline0, int):
            baseline0 = max(0, h - 2)
        baseline_page = y + baseline0

        style = str(row.get("style") or meta.get("style") or "bold")
        above, below = extents.get(style, (global_above, global_below))
        new_y0 = max(0, baseline_page - above - safety)
        new_y1 = min(image.height, baseline_page + below + safety + 1)
        if new_y1 <= new_y0:
            continue

        crop = image.crop((x, new_y0, x + w, new_y1))
        rel = str(row.get("word_file") or "")
        if not rel:
            continue
        target = args.library / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        crop.save(target)

        row["width"] = w
        row["height"] = new_y1 - new_y0
        row["baseline_y"] = baseline_page - new_y0
        row["vertical_crop"] = {
            "style": style,
            "above": above,
            "below": below,
            "safety": safety,
            "page_y0": new_y0,
            "page_y1": new_y1,
        }
        changed += 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(batch, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("style_extents:")
    for style in sorted(extents):
        above, below = extents[style]
        print(f"  {style}: above={above} below={below} safety={safety}")
    print(f"recropped={changed}")
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
