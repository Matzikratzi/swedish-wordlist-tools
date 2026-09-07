from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from PIL import Image

from . import ocr_prepare_sequential_page as sequential_page

_BASE_RELATIVE_CONTEXT = sequential_page._relative_five_row_context


def _target_first_line_context(
    page: Image.Image,
    line_context: dict[str, Any] | None,
    threshold: int,
) -> dict[str, Any] | None:
    """Analyse only the target row unless ink really crosses into a neighbour."""
    if not line_context or not line_context.get("bands_page"):
        return line_context

    bands = list(line_context["bands_page"])
    target = int(line_context["target_index"])
    column_left = int(line_context.get("column_left", 0))
    column_right = int(line_context.get("column_right", page.width))
    active = {target}

    upper = target - 1
    if upper >= 0 and sequential_page._rows_share_black_component(
        page, bands, upper, target, column_left, column_right, threshold
    ):
        active.add(upper)
        upper_outer = target - 2
        if upper_outer >= 0 and sequential_page._rows_share_black_component(
            page, bands, upper_outer, upper, column_left, column_right, threshold
        ):
            active.add(upper_outer)

    lower = target + 1
    if lower < len(bands) and sequential_page._rows_share_black_component(
        page, bands, target, lower, column_left, column_right, threshold
    ):
        active.add(lower)
        lower_outer = target + 2
        if lower_outer < len(bands) and sequential_page._rows_share_black_component(
            page, bands, lower, lower_outer, column_left, column_right, threshold
        ):
            active.add(lower_outer)

    indices = sorted(active)
    selected = [dict(bands[i]) for i in indices]
    return {
        **line_context,
        "bands_page": selected,
        "target_index": indices.index(target),
        "source_band_indices": indices,
        "neighbor_support_rows": [i for i in indices if abs(i - target) == 1],
        "outer_support_rows": [i for i in indices if abs(i - target) == 2],
        "analysis_window": "target-first-connected-neighbours",
        "all_bands_page": [dict(band) for band in bands],
        "all_target_index": target,
    }


def _relative_target_first_context(
    line_context: dict[str, Any] | None,
    crop_box: tuple[int, int, int, int],
) -> dict[str, Any] | None:
    relative = _BASE_RELATIVE_CONTEXT(line_context, crop_box)
    if relative is None or not line_context:
        return relative

    all_bands = line_context.get("all_bands_page") or []
    all_target = line_context.get("all_target_index")
    if not all_bands or not isinstance(all_target, int):
        return relative

    _, y0, _, _ = crop_box
    source_bands = []
    for band in all_bands:
        top = int(band["top"])
        bottom = int(band["bottom"])
        source_bands.append(
            {
                "top": top - y0,
                "bottom": bottom - y0,
                "page_top": top,
                "page_bottom": bottom,
                "text": str(band.get("text") or ""),
            }
        )
    relative["source_bands"] = source_bands
    relative["source_target_index"] = all_target
    return relative


def _cache_row_artifacts(out_dir: Path, cache_dir: Path) -> None:
    prepared = cache_dir / "prepared"
    prepared.mkdir(parents=True, exist_ok=True)
    for name in ("page-row-map.json", "row-map-ocr.json"):
        source = out_dir / name
        if source.is_file():
            shutil.copy2(source, prepared / name)
    for source in out_dir.glob("saol14-word-debug-*-rowmap-*.json"):
        shutil.copy2(source, prepared / source.name)
    source_png = out_dir / "png"
    cached_png = prepared / "png"
    cached_png.mkdir(exist_ok=True)
    if source_png.is_dir():
        for source in source_png.glob("saol14-word-debug-*-rowmap-*.png"):
            shutil.copy2(source, cached_png / source.name)


def main() -> int:
    sequential_page._active_line_context = _target_first_line_context
    sequential_page._relative_five_row_context = _relative_target_first_context

    from . import ocr_page_row_guides as row_guides
    from . import ocr_row_map_words as row_words
    from . import ocr_unique_unknown_glyph_review as unique
    from . import ocr_sequential_page_review_persistent as persistent

    # v4 adds row-map-owned OCR and supplemental debug rows to the prepared cache.
    persistent.PREP_CACHE_VERSION = "saol-page-prep-target-first-v4"
    persistent.ANALYSIS_CACHE_VERSION = "saol-row-analysis-target-first-v3"

    unique.unknown_groups = row_guides.target_unknown_groups
    unique._cropped_review_context = row_guides.wrap_review_context(unique._cropped_review_context)
    unique._jsonl_group_suggestions = row_guides.wrap_jsonl_group_suggestions(
        unique._jsonl_group_suggestions
    )

    cached_prepare = persistent._cached_prepare_page

    def cached_prepare_with_row_map(
        jsonl: Path,
        page_number: int,
        out_dir: Path,
        **kwargs: Any,
    ) -> dict:
        report = cached_prepare(jsonl, page_number, out_dir, **kwargs)
        out_dir = Path(out_dir)
        row_map_path = out_dir / "page-row-map.json"
        row_ocr_path = out_dir / "row-map-ocr.json"
        page_image = sequential_page._load_source_image(str(report.get("source") or ""))
        if page_image is None:
            raise RuntimeError("could not load page image for physical-row OCR")

        row_map = row_guides.write_page_row_map(
            out_dir,
            row_map_path,
            page_image=page_image,
            threshold=int(kwargs.get("threshold", 210)),
        )
        print(
            f"[row-map] {row_map.get('row_count', 0)} physical rows "
            f"({row_map.get('proposed_row_count', 0)} lattice); "
            f"cached={row_map_path}",
            flush=True,
        )

        if row_ocr_path.is_file():
            payload = json.loads(row_ocr_path.read_text(encoding="utf-8"))
            records = list(payload.get("words") or [])
        else:
            print(
                f"[row-ocr] recognizing {row_map.get('row_count', 0)} physical rows with psm=7...",
                flush=True,
            )
            records = row_words.write_row_map_ocr(
                page_image,
                row_map,
                jsonl,
                page_number,
                row_ocr_path,
                lang=str(kwargs.get("lang", "swe")),
                psm=7,
                pad_y=1,
            )

        supplemental = row_words.write_lattice_debug_files(
            page_image,
            records,
            out_dir,
            page_number=page_number,
            source=str(report.get("source") or ""),
            threshold=int(kwargs.get("threshold", 210)),
        )
        lattice_words = sum(
            1 for record in records if record.get("row_source") == "white-gap-ink-island"
        )
        print(
            f"[row-ocr] words={len(records)} lattice_words={lattice_words} "
            f"supplemental_anchored={supplemental}; cached={row_ocr_path}",
            flush=True,
        )

        cache_dir = persistent._ACTIVE_PAGE_CACHE
        if cache_dir is not None:
            _cache_row_artifacts(out_dir, cache_dir)
        return report

    persistent._cached_prepare_page = cached_prepare_with_row_map
    return persistent.main()


if __name__ == "__main__":
    raise SystemExit(main())
