from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Iterable

from PIL import Image

from . import ocr_prepare_next20_glyph_words as prep


def _safe(s: str) -> str:
    s = re.sub(r"[^0-9A-Za-zÅÄÖåäöÉéÀàÇçÑñ_-]+", "_", s).strip("_")
    return s[:60] or "word"


def _black_pixels(im: Image.Image, threshold: int) -> list[list[int]]:
    gray = im.convert("L")
    return [[x, y] for y in range(gray.height) for x in range(gray.width) if gray.getpixel((x, y)) < threshold]


def _bbox(row: dict[str, Any]) -> list[int] | None:
    for key in ("page_word_bbox", "word_bbox", "bbox", "box"):
        value = row.get(key)
        if isinstance(value, (list, tuple)) and len(value) == 4:
            try:
                return [int(v) for v in value]
            except (TypeError, ValueError):
                pass
    # Also accept explicit x/y/w/h fields.
    aliases = (
        ("x", "y", "w", "h"),
        ("left", "top", "width", "height"),
        ("x", "y", "width", "height"),
    )
    for names in aliases:
        if all(name in row for name in names):
            try:
                return [int(row[name]) for name in names]
            except (TypeError, ValueError):
                pass
    return None


def _word(row: dict[str, Any]) -> str:
    for key in ("expected_word", "source_word", "stycke", "lemma", "headword", "word", "writtenForm", "written_form"):
        value = row.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _page(row: dict[str, Any]) -> str:
    for key in ("page", "page_number", "sidnr"):
        value = row.get(key)
        if value is not None:
            return str(value)
    source = str(row.get("source") or row.get("page_image") or "")
    m = re.search(r"SAOL14_(\d{5})\.png", source)
    return str(int(m.group(1))) if m else ""


def _subnr(row: dict[str, Any]) -> str:
    for key in ("subnr", "record_id", "id"):
        value = row.get(key)
        if value is not None:
            return str(value)
    return ""


def _normalise_meta(row: dict[str, Any]) -> dict[str, Any] | None:
    bbox = _bbox(row)
    if bbox is None:
        return None
    meta = dict(row)
    meta["page_word_bbox"] = bbox
    meta.setdefault("expected_word", _word(row))
    meta.setdefault("page", _page(row))
    meta.setdefault("subnr", _subnr(row))
    if not meta.get("page_image"):
        for key in ("source", "image", "image_path", "page_source"):
            value = row.get(key)
            if isinstance(value, str) and value:
                meta["page_image"] = value
                break
    return meta


def _manifest_rows(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in (manifest.get("template_sources") or {}).values():
        if not isinstance(row, dict):
            continue
        meta = _normalise_meta(row)
        if meta is not None:
            out.append(meta)
    return out


def _jsonl_rows(path: Path) -> tuple[list[dict[str, Any]], set[str]]:
    out: list[dict[str, Any]] = []
    observed_keys: set[str] = set()
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue
            observed_keys.update(str(k) for k in row)
            meta = _normalise_meta(row)
            if meta is not None:
                out.append(meta)
    return out, observed_keys


def _index_rows(rows: Iterable[dict[str, Any]]) -> tuple[dict[tuple[str, str, str], dict[str, Any]], dict[tuple[str, str], list[dict[str, Any]]]]:
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


def match_selection_rows(selection: dict[str, Any], rows: Iterable[dict[str, Any]]) -> tuple[list[tuple[dict[str, Any], dict[str, Any]]], list[dict[str, Any]]]:
    exact, by_page_word = _index_rows(rows)
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


def match_selection(selection: dict[str, Any], manifest: dict[str, Any]) -> tuple[list[tuple[dict[str, Any], dict[str, Any]]], list[dict[str, Any]]]:
    return match_selection_rows(selection, _manifest_rows(manifest))


def discover_manifest(root: Path = Path(".")) -> Path | None:
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
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def crop_selection_rows(selection_path: Path, rows: list[dict[str, Any]], out_dir: Path, *, threshold: int = 210, save_png: bool = True) -> dict[str, Any]:
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    matched, missing = match_selection_rows(selection, rows)
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
                failures.append({"expected_word": sel.get("expected_word"), "reason": "page-image-unavailable", "page_key": page_key})
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
            "page_source": meta.get("source") or meta.get("page_image"),
        }
        (out_dir / f"{stem}.json").write_text(json.dumps(debug, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written += 1

    return {
        "selected": len(selection.get("words") or []),
        "matched": len(matched),
        "missing": missing,
        "word_debug_files": written,
        "crop_failures": failures,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Crop selected unknown-glyph words from a SAOL facsimile manifest or directly from SAOL JSONL.")
    ap.add_argument("selection", type=Path)
    ap.add_argument("source", nargs="?", type=Path, help="manifest JSON or SAOL JSONL; if omitted, try manifest then selection's jsonl")
    ap.add_argument("--jsonl", type=Path, help="explicit SAOL JSONL source")
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--no-png", action="store_true")
    args = ap.parse_args()

    selection = json.loads(args.selection.read_text(encoding="utf-8"))
    source = args.jsonl or args.source
    source_kind = ""
    observed_keys: set[str] = set()

    if source is None:
        manifest = discover_manifest()
        if manifest is not None:
            source = manifest
        else:
            candidate = selection.get("jsonl")
            if isinstance(candidate, str) and candidate:
                source = Path(candidate)

    if source is None or not source.exists():
        raise FileNotFoundError("no manifest found and no readable SAOL JSONL source available")

    if source.suffix.lower() == ".jsonl":
        rows, observed_keys = _jsonl_rows(source)
        source_kind = "jsonl"
    else:
        manifest = json.loads(source.read_text(encoding="utf-8"))
        rows = _manifest_rows(manifest)
        source_kind = "manifest"

    if not rows:
        keys = ", ".join(sorted(observed_keys)) if observed_keys else "(none)"
        raise SystemExit(
            "source contains no usable word bounding boxes. "
            "Expected page_word_bbox/word_bbox/bbox/box or x,y,w,h fields. "
            f"Observed JSONL keys: {keys}"
        )

    report = crop_selection_rows(args.selection, rows, args.out_dir, threshold=args.threshold, save_png=not args.no_png)
    print(f"source={source}")
    print(f"source_kind={source_kind}")
    print(f"bbox_rows={len(rows)}")
    print(f"selected={report['selected']}")
    print(f"matched={report['matched']}")
    print(f"missing={len(report['missing'])}")
    print(f"word_debug_files={report['word_debug_files']}")
    print(f"crop_failures={len(report['crop_failures'])}")
    if report["missing"]:
        print("missing_examples=" + ", ".join(str(r.get("expected_word") or "?") for r in report["missing"][:12]))
    if report["crop_failures"]:
        print("crop_failure_examples=" + ", ".join(str(r.get("expected_word") or "?") for r in report["crop_failures"][:12]))
    print(args.out_dir)
    return 0 if report["word_debug_files"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
