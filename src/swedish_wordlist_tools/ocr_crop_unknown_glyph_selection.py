from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from PIL import Image

from . import ocr_prepare_next20_glyph_words as prep


def _safe(s: str) -> str:
    s = re.sub(r"[^0-9A-Za-zÅÄÖåäöÉéÀàÇçÑñ_-]+", "_", s).strip("_")
    return s[:60] or "word"


def _black_pixels(im: Image.Image, threshold: int) -> list[list[int]]:
    gray = im.convert("L")
    return [[x, y] for y in range(gray.height) for x in range(gray.width) if gray.getpixel((x, y)) < threshold]


def _manifest_rows(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in (manifest.get("template_sources") or {}).values():
        if not isinstance(row, dict):
            continue
        bbox = row.get("page_word_bbox")
        if isinstance(bbox, list) and len(bbox) == 4:
            out.append(row)
    return out


def _index_manifest(rows: list[dict[str, Any]]) -> tuple[dict[tuple[str, str, str], dict[str, Any]], dict[tuple[str, str], list[dict[str, Any]]]]:
    exact: dict[tuple[str, str, str], dict[str, Any]] = {}
    by_page_word: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        page = str(row.get("page") or "")
        subnr = str(row.get("subnr") or "")
        word = str(row.get("expected_word") or row.get("source_word") or "")
        if not word:
            continue
        exact.setdefault((page, subnr, word), row)
        by_page_word.setdefault((page, word), []).append(row)
    return exact, by_page_word


def match_selection(selection: dict[str, Any], manifest: dict[str, Any]) -> tuple[list[tuple[dict[str, Any], dict[str, Any]]], list[dict[str, Any]]]:
    exact, by_page_word = _index_manifest(_manifest_rows(manifest))
    matched: list[tuple[dict[str, Any], dict[str, Any]]] = []
    missing: list[dict[str, Any]] = []
    for sel in selection.get("words") or []:
        if not isinstance(sel, dict):
            continue
        page = str(sel.get("page") or "")
        subnr = str(sel.get("subnr") or "")
        word = str(sel.get("expected_word") or "")
        row = exact.get((page, subnr, word))
        if row is None:
            candidates = by_page_word.get((page, word), [])
            if len(candidates) == 1:
                row = candidates[0]
        if row is None:
            missing.append(sel)
        else:
            matched.append((sel, row))
    return matched, missing


def discover_manifest(root: Path = Path(".")) -> Path:
    candidates: list[tuple[int, Path]] = []
    for path in root.rglob("*.json"):
        if any(part in {".git", ".venv", "venv", "tests", "node_modules"} for part in path.parts):
            continue
        try:
            with path.open(encoding="utf-8") as f:
                payload = json.load(f)
        except Exception:
            continue
        if isinstance(payload, dict) and isinstance(payload.get("template_sources"), dict):
            candidates.append((len(payload["template_sources"]), path))
    if not candidates:
        raise FileNotFoundError("could not auto-discover a manifest containing template_sources")
    candidates.sort(reverse=True)
    return candidates[0][1]


def crop_selection(selection_path: Path, manifest_path: Path, out_dir: Path, *, threshold: int = 210, save_png: bool = True) -> dict[str, Any]:
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    matched, missing = match_selection(selection, manifest)
    out_dir.mkdir(parents=True, exist_ok=True)
    png_dir = out_dir / "png"
    if save_png:
        png_dir.mkdir(exist_ok=True)

    page_cache: dict[str, Image.Image] = {}
    written = 0
    failures: list[dict[str, Any]] = []
    for i, (sel, meta) in enumerate(matched):
        page_key = str(meta.get("page_image") or meta.get("source") or meta.get("page") or "")
        image = page_cache.get(page_key)
        if image is None:
            image = prep._load_page_image(meta)
            if image is None:
                failures.append({"expected_word": sel.get("expected_word"), "reason": "page-image-unavailable"})
                continue
            page_cache[page_key] = image

        x, y, w, h = [int(v) for v in meta["page_word_bbox"]]
        x = max(0, x); y = max(0, y)
        w = max(1, min(w, image.width - x)); h = max(1, min(h, image.height - y))
        crop = image.crop((x, y, x + w, y + h)).convert("L")
        word = str(sel.get("expected_word") or "")
        page = sel.get("page")
        subnr = sel.get("subnr")
        stem = f"{i:03d}-p{page}-sub{subnr}-{_safe(word)}"
        if save_png:
            crop.save(png_dir / f"{stem}.png")
        debug = {
            "format": "saol14-word-debug-v1",
            "expected_word": word,
            "headword": word,
            "page": page,
            "subnr": subnr,
            "style": str(meta.get("style") or "bold"),
            "width": crop.width,
            "height": crop.height,
            "black_pixels": _black_pixels(crop, threshold),
            "harvest_half": sel.get("harvest_half"),
            "unknown_label": sel.get("unknown_label"),
            "unknown_index": sel.get("unknown_index"),
            "source_id": f"{page}:{subnr}:{word}",
            "page_word_bbox": [x, y, w, h],
            "page_source": meta.get("source"),
        }
        (out_dir / f"{stem}.json").write_text(json.dumps(debug, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written += 1

    return {
        "selected": len(selection.get("words") or []),
        "manifest_matched": len(matched),
        "manifest_missing": len(missing),
        "word_debug_files": written,
        "crop_failures": failures,
        "missing": missing,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Crop selected unknown-glyph words from the SAOL facsimile manifest and write word-debug JSON files.")
    ap.add_argument("selection", type=Path)
    ap.add_argument("manifest", nargs="?", type=Path, help="manifest with template_sources; auto-discovered if omitted")
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--no-png", action="store_true")
    args = ap.parse_args()
    manifest = args.manifest or discover_manifest()
    report = crop_selection(args.selection, manifest, args.out_dir, threshold=args.threshold, save_png=not args.no_png)
    print(f"manifest={manifest}")
    for key in ("selected", "manifest_matched", "manifest_missing", "word_debug_files"):
        print(f"{key}={report[key]}")
    print(f"crop_failures={len(report['crop_failures'])}")
    if report["missing"]:
        print("missing_examples=" + ", ".join(str(r.get("expected_word") or "?") for r in report["missing"][:12]))
    print(args.out_dir)
    return 0 if report["word_debug_files"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
