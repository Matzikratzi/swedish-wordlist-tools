from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image

from .ocr_glyph_templates import _trim


def _inventory(style_dir: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    if style_dir.exists():
        for path in style_dir.glob("*.png"):
            label = path.name.split("-", 1)[0]
            counts[label] = counts.get(label, 0) + 1
    return dict(sorted(counts.items()))


def _source_key(meta: dict[str, object]) -> tuple[object, ...] | None:
    bbox = meta.get("bbox")
    if not isinstance(bbox, list) or len(bbox) != 4:
        return None
    return (
        meta.get("style"),
        meta.get("character"),
        meta.get("page"),
        meta.get("column"),
        tuple(int(v) for v in bbox),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply manually reviewed glyph bboxes to a mined library and deduplicate identical source glyphs.")
    parser.add_argument("library", type=Path)
    parser.add_argument("overrides", type=Path)
    parser.add_argument("--no-deduplicate", action="store_true")
    args = parser.parse_args()

    manifest_path = args.library / "manifest-pages.json"
    if not manifest_path.exists():
        raise SystemExit(f"missing manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    sources = manifest.get("template_sources")
    if not isinstance(sources, dict):
        raise SystemExit("manifest has no template_sources map")

    override_doc = json.loads(args.overrides.read_text(encoding="utf-8"))
    overrides = override_doc.get("overrides", override_doc)
    if not isinstance(overrides, dict):
        raise SystemExit("override file must contain an overrides object")

    applied: list[dict[str, object]] = []
    missing: list[str] = []
    for key, override in overrides.items():
        if not isinstance(key, str) or not isinstance(override, dict):
            continue
        meta = sources.get(key)
        if not isinstance(meta, dict):
            missing.append(key)
            continue
        bbox = override.get("bbox")
        if not isinstance(bbox, list) or len(bbox) != 4:
            continue
        bbox = [int(v) for v in bbox]
        image_path = meta.get("column_image")
        if not isinstance(image_path, str) or not Path(image_path).exists():
            missing.append(key)
            continue
        x, y, w, h = bbox
        if w <= 0 or h <= 0:
            continue
        with Image.open(image_path) as im0:
            im = im0.convert("L")
            if x < 0 or y < 0 or x + w > im.width or y + h > im.height:
                missing.append(key)
                continue
            glyph = _trim(im.crop((x, y, x + w, y + h)))
        out = args.library / key
        out.parent.mkdir(parents=True, exist_ok=True)
        glyph.save(out)
        old_bbox = meta.get("bbox")
        meta["bbox"] = bbox
        column_left = int(meta.get("column_left") or 0)
        meta["page_bbox"] = [bbox[0] + column_left, bbox[1], bbox[2], bbox[3]]
        meta["manual_override"] = True
        applied.append({"key": key, "old_bbox": old_bbox, "new_bbox": bbox})

    removed: list[dict[str, object]] = []
    if not args.no_deduplicate:
        seen: dict[tuple[object, ...], str] = {}
        for key in list(sources):
            meta = sources.get(key)
            if not isinstance(meta, dict):
                continue
            source_key = _source_key(meta)
            if source_key is None:
                continue
            previous = seen.get(source_key)
            if previous is None:
                seen[source_key] = key
                continue
            # Prefer a manually corrected instance as the canonical file.
            prev_meta = sources.get(previous)
            prefer_current = bool(meta.get("manual_override")) and not bool(isinstance(prev_meta, dict) and prev_meta.get("manual_override"))
            keep, drop = (key, previous) if prefer_current else (previous, key)
            if prefer_current:
                seen[source_key] = key
            drop_path = args.library / drop
            if drop_path.exists():
                drop_path.unlink()
            sources.pop(drop, None)
            removed.append({"kept": keep, "removed": drop, "source": list(source_key)})

    manifest["template_sources"] = sources
    styles = manifest.get("styles", [])
    if isinstance(styles, list):
        manifest["library_after_overrides"] = {
            str(style): _inventory(args.library / str(style)) for style in styles
        }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report = {
        "applied_count": len(applied),
        "applied": applied,
        "missing_count": len(missing),
        "missing": missing,
        "deduplicated_count": len(removed),
        "deduplicated": removed,
    }
    (args.library / "manifest-overrides.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    json.dump(report, __import__("sys").stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
