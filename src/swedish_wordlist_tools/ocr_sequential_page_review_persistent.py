from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path

from . import ocr_prepare_sequential_page as sequential_page
from . import ocr_sequential_page_review as base
from . import ocr_sequential_page_review_cached as row_cached

PREP_CACHE_VERSION = "saol-page-prep-12area-v1"
ANALYSIS_CACHE_VERSION = "saol-row-analysis-12area-v1"
AREA_COLUMNS = 3
AREA_ROWS = 4
_ORIGINAL_PREPARE_PAGE = sequential_page.prepare_page
_ORIGINAL_ANALYSE_PATHS = row_cached._analyse_paths
_ACTIVE_PAGE_CACHE: Path | None = None


def _default_cache_root() -> Path:
    value = os.environ.get("SAOL_OCR_CACHE")
    if value:
        return Path(value).expanduser()
    return Path.home() / ".cache" / "swedish-wordlist-tools" / "saol-ocr"


def _file_signature(path: Path) -> dict:
    stat = path.stat()
    return {
        "path": str(path.resolve()),
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }


def _prep_signature(
    jsonl: Path,
    page_number: int,
    *,
    threshold: int,
    lang: str,
    psm: int,
    pad_x: int,
    pad_y: int,
    min_confidence: float,
) -> dict:
    return {
        "version": PREP_CACHE_VERSION,
        "jsonl": _file_signature(jsonl),
        "page": page_number,
        "threshold": threshold,
        "lang": lang,
        "psm": psm,
        "pad_x": pad_x,
        "pad_y": pad_y,
        "min_confidence": min_confidence,
    }


def _digest_json(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _facit_digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _copy_tree_contents(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for child in source.iterdir():
        target = destination / child.name
        if child.is_dir():
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(child, target)
        else:
            shutil.copy2(child, target)


def _area_for_bbox(bbox: list | tuple | None, page_width: int, page_height: int) -> str:
    if not bbox or len(bbox) != 4:
        return "c1-r1"
    left, top, width, height = (int(v) for v in bbox)
    cx = left + width / 2
    cy = top + height / 2
    column = max(0, min(AREA_COLUMNS - 1, int(AREA_COLUMNS * cx / max(1, page_width))))
    row = max(0, min(AREA_ROWS - 1, int(AREA_ROWS * cy / max(1, page_height))))
    return f"c{column + 1}-r{row + 1}"


def _annotate_cache_areas(prepared_dir: Path, report: dict) -> None:
    page_size = report.get("page_size") or [1, 1]
    page_width, page_height = int(page_size[0]), int(page_size[1])
    counts: dict[str, int] = {}
    for path in prepared_dir.glob("saol14-word-debug-*.json"):
        debug = json.loads(path.read_text(encoding="utf-8"))
        tesseract = debug.get("tesseract") or {}
        bbox = tesseract.get("raw_bbox") or debug.get("page_word_bbox")
        area = _area_for_bbox(bbox, page_width, page_height)
        debug["cache_area"] = area
        path.write_text(json.dumps(debug, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        counts[area] = counts.get(area, 0) + 1
    manifest = {
        "format": "saol-ocr-12-area-cache-v1",
        "page": report.get("page"),
        "page_size": [page_width, page_height],
        "areas": {f"c{c}-r{r}": counts.get(f"c{c}-r{r}", 0) for r in range(1, 5) for c in range(1, 4)},
    }
    (prepared_dir / "area-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _cached_prepare_page(
    jsonl: Path,
    page_number: int,
    out_dir: Path,
    *,
    threshold: int = 210,
    lang: str = "swe",
    psm: int = 4,
    pad_x: int = 1,
    pad_y: int = 5,
    min_confidence: float = -1.0,
) -> dict:
    global _ACTIVE_PAGE_CACHE
    signature = _prep_signature(
        jsonl,
        page_number,
        threshold=threshold,
        lang=lang,
        psm=psm,
        pad_x=pad_x,
        pad_y=pad_y,
        min_confidence=min_confidence,
    )
    cache_root = _default_cache_root()
    cache_dir = cache_root / f"page-{page_number:05d}" / _digest_json(signature)[:20]
    prepared_dir = cache_dir / "prepared"
    report_path = prepared_dir / "page-report.json"

    if report_path.is_file():
        print(f"[prepare-cache] HIT {cache_dir}", flush=True)
        _copy_tree_contents(prepared_dir, out_dir)
        _ACTIVE_PAGE_CACHE = cache_dir
        return json.loads((out_dir / "page-report.json").read_text(encoding="utf-8"))

    print(f"[prepare-cache] MISS {cache_dir}", flush=True)
    if cache_dir.exists():
        shutil.rmtree(cache_dir)
    prepared_dir.mkdir(parents=True, exist_ok=True)
    report = _ORIGINAL_PREPARE_PAGE(
        jsonl,
        page_number,
        prepared_dir,
        threshold=threshold,
        lang=lang,
        psm=psm,
        pad_x=pad_x,
        pad_y=pad_y,
        min_confidence=min_confidence,
    )
    _annotate_cache_areas(prepared_dir, report)
    (cache_dir / "signature.json").write_text(
        json.dumps(signature, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    _copy_tree_contents(prepared_dir, out_dir)
    _ACTIVE_PAGE_CACHE = cache_dir
    return report


def _area_for_path(path: Path) -> str:
    debug = json.loads(path.read_text(encoding="utf-8"))
    return str(debug.get("cache_area") or "c1-r1")


def _analysis_cache_key(paths: list[Path], facit_path: Path) -> str:
    group_keys = [repr(row_cached._debug_row_key(path)) for path in paths]
    value = {
        "version": ANALYSIS_CACHE_VERSION,
        "facit_sha256": _facit_digest(facit_path),
        "row_keys": group_keys,
    }
    return _digest_json(value)[:20]


def _cached_analyse_paths(paths: list[Path], facit_path: Path, workers: int) -> list[dict]:
    if not paths:
        return []
    if _ACTIVE_PAGE_CACHE is None:
        return _ORIGINAL_ANALYSE_PATHS(paths, facit_path, workers)

    by_area: dict[str, list[tuple[int, Path]]] = {}
    for index, path in enumerate(paths):
        by_area.setdefault(_area_for_path(path), []).append((index, path))

    rows: list[dict | None] = [None] * len(paths)
    hits = 0
    missing_areas: list[tuple[str, list[tuple[int, Path]], Path]] = []
    for area in sorted(by_area):
        items = by_area[area]
        area_paths = [path for _, path in items]
        key = _analysis_cache_key(area_paths, facit_path)
        cache_path = _ACTIVE_PAGE_CACHE / "analysis" / area / f"{key}.json"
        if cache_path.is_file():
            area_rows = json.loads(cache_path.read_text(encoding="utf-8"))
            if len(area_rows) == len(items):
                hits += 1
                for (index, _), row in zip(items, area_rows):
                    rows[index] = row
                continue
        missing_areas.append((area, items, cache_path))

    if missing_areas:
        missing_items = [item for _, items, _ in missing_areas for item in items]
        missing_paths = [path for _, path in missing_items]
        analysed_missing = _ORIGINAL_ANALYSE_PATHS(missing_paths, facit_path, workers)
        analysed_by_index = {
            original_index: row
            for (original_index, _), row in zip(missing_items, analysed_missing)
        }
        for area, items, cache_path in missing_areas:
            area_rows = [analysed_by_index[index] for index, _ in items]
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(area_rows, ensure_ascii=False) + "\n", encoding="utf-8")
            for (index, _), row in zip(items, area_rows):
                rows[index] = row

    print(
        f"[analysis-cache] areas={len(by_area)} hits={hits} misses={len(missing_areas)} "
        f"facit={_facit_digest(facit_path)[:12]}",
        flush=True,
    )
    return [row for row in rows if row is not None]


def main() -> int:
    sequential_page.prepare_page = _cached_prepare_page
    base.sequential_page.prepare_page = _cached_prepare_page
    base._analyse_paths = _cached_analyse_paths
    return base.main()


if __name__ == "__main__":
    raise SystemExit(main())
