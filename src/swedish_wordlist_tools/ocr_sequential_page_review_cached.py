from __future__ import annotations

import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from . import ocr_exact_glyph_review_queue_v12 as review_v12
from . import ocr_sequential_page_review as base
from .ocr_glyph_matcher import load_facit

_ORIGINAL_EXTRACT = review_v12._extract_exact_rows_from_tangle
_WORKER_MODELS = None
_TANGLE_CACHE: dict[tuple, tuple] = {}


def _debug_row_key(path: Path) -> tuple:
    """Return the physical analysis-raster identity for one word-debug file.

    Wide-row page preparation deliberately gives every word on one physical
    target line the same page crop.  Those words therefore have identical ink,
    neighbour bands and expensive exact-glyph tangle analysis; only the final
    target-word x projection differs.
    """
    debug = json.loads(path.read_text(encoding="utf-8"))
    bbox = debug.get("page_word_bbox") or []
    context = debug.get("five_row_context") or {}
    source_band_indices = context.get("source_band_indices") or []
    return (
        tuple(int(v) for v in bbox) if len(bbox) == 4 else tuple(bbox),
        int(context.get("target_index", -1)),
        tuple(int(v) for v in source_band_indices),
    )


def _group_paths(paths: list[Path]) -> list[list[tuple[int, Path]]]:
    grouped: dict[tuple, list[tuple[int, Path]]] = {}
    order: list[tuple] = []
    for index, path in enumerate(paths):
        key = _debug_row_key(path)
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append((index, path))
    return [grouped[key] for key in order]


def _tangle_cache_key(ink, width: int, height: int, bands: list[dict]) -> tuple:
    band_geometry = tuple((int(b["top"]), int(b["bottom"])) for b in bands)
    return width, height, band_geometry, frozenset(ink)


def _cached_extract(ink, width, height, models, bands):
    key = _tangle_cache_key(ink, width, height, bands)
    cached = _TANGLE_CACHE.get(key)
    if cached is None:
        cached = _ORIGINAL_EXTRACT(ink, width, height, models, bands)
        _TANGLE_CACHE[key] = cached
    return cached


def _init_worker(facit_path: str) -> None:
    global _WORKER_MODELS, _TANGLE_CACHE
    _WORKER_MODELS = load_facit(Path(facit_path))
    _TANGLE_CACHE = {}
    review_v12._extract_exact_rows_from_tangle = _cached_extract


def _analyse_group_worker(items: list[tuple[int, str]]) -> list[tuple[int, dict]]:
    if _WORKER_MODELS is None:
        raise RuntimeError("OCR analysis worker was not initialized")
    return [
        (index, base._analyse_with_debug_metadata(Path(path_text), _WORKER_MODELS))
        for index, path_text in items
    ]


def _analyse_paths(paths: list[Path], facit_path: Path, workers: int) -> list[dict]:
    if not paths:
        return []

    groups = _group_paths(paths)
    workers = max(1, min(int(workers), len(groups)))
    print(
        f"[cache] {len(paths)} anchored words share {len(groups)} physical row rasters; "
        f"avoiding {len(paths) - len(groups)} duplicate wide-row analyses",
        flush=True,
    )
    base._print_progress(0, len(groups), workers, force=True)

    rows: list[dict | None] = [None] * len(paths)
    if workers == 1:
        _init_worker(str(facit_path))
        for done, group in enumerate(groups, 1):
            for index, row in _analyse_group_worker(
                [(index, str(path)) for index, path in group]
            ):
                rows[index] = row
            base._print_progress(done, len(groups), workers)
    else:
        with ProcessPoolExecutor(
            max_workers=workers,
            initializer=_init_worker,
            initargs=(str(facit_path),),
        ) as executor:
            futures = {
                executor.submit(
                    _analyse_group_worker,
                    [(index, str(path)) for index, path in group],
                ): group
                for group in groups
            }
            for done, future in enumerate(as_completed(futures), 1):
                for index, row in future.result():
                    rows[index] = row
                base._print_progress(done, len(groups), workers)

    return [row for row in rows if row is not None]


def main() -> int:
    # Keep the established CLI/report/review pipeline; only replace its expensive
    # per-word analysis stage with physical-row grouped analysis.
    base._analyse_paths = _analyse_paths
    return base.main()


if __name__ == "__main__":
    raise SystemExit(main())
