from __future__ import annotations

import copy
import hashlib
import json
import os
import threading
from pathlib import Path
from typing import Iterable

from PIL import Image

from .ocr_glyph_matcher import GlyphModel
from .ocr_group_baseline_fallback import analyse_row_exact_grouped_with_baseline_fallback


BOUNDARY_ALGORITHM_VERSION = 1
GEOMETRY_COMPAT_VERSION = 1
DEFAULT_CACHE_PATH = Path("data/generated/ocr-page-cache/row-boundary-corrections-v1.json")


def page_digest(page_image: Image.Image) -> str:
    """Stable digest for the raster whose learned boundaries are being cached."""
    gray = page_image.convert("L")
    digest = hashlib.sha256()
    digest.update(f"{gray.width}x{gray.height}:L\n".encode("ascii"))
    digest.update(gray.tobytes())
    return digest.hexdigest()


def model_digest(models: Iterable[GlyphModel]) -> str:
    """Diagnostic signature of the glyph evidence used to prove a correction.

    It is deliberately stored as evidence metadata, not as part of the cache key.
    Adding a glyph later must not make a previously proven physical boundary
    disappear from the cache.
    """
    rows = []
    for model in models:
        rows.append(
            (
                model.label,
                model.style,
                tuple(sorted(model.pixels)),
                int(model.sources),
            )
        )
    return hashlib.sha256(repr(sorted(rows)).encode("utf-8")).hexdigest()


def _cache_key(
    *,
    source_digest: str,
    page_number: int,
    threshold: int,
    column: int,
    upper_row: int,
) -> str:
    return ":".join(
        [
            f"algo{BOUNDARY_ALGORITHM_VERSION}",
            f"geom{GEOMETRY_COMPAT_VERSION}",
            source_digest,
            f"p{int(page_number)}",
            f"t{int(threshold)}",
            f"c{int(column)}",
            f"r{int(upper_row)}-{int(upper_row) + 1}",
        ]
    )


class BoundaryCorrectionStore:
    """Small persistent JSON cache for learned horizontal row boundaries."""

    def __init__(self, path: Path = DEFAULT_CACHE_PATH):
        self.path = Path(path)
        self._lock = threading.RLock()
        self._loaded = False
        self._records: dict[str, dict] = {}

    def _load(self) -> None:
        with self._lock:
            if self._loaded:
                return
            self._loaded = True
            if not self.path.exists():
                return
            try:
                payload = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return
            if not isinstance(payload, dict):
                return
            records = payload.get("records")
            if isinstance(records, dict):
                self._records = {
                    str(key): dict(value)
                    for key, value in records.items()
                    if isinstance(value, dict)
                }

    def get(
        self,
        *,
        source_digest: str,
        page_number: int,
        threshold: int,
        column: int,
        upper_row: int,
    ) -> dict | None:
        self._load()
        key = _cache_key(
            source_digest=source_digest,
            page_number=page_number,
            threshold=threshold,
            column=column,
            upper_row=upper_row,
        )
        with self._lock:
            row = self._records.get(key)
            return copy.deepcopy(row) if row is not None else None

    def put(self, record: dict) -> None:
        self._load()
        key = _cache_key(
            source_digest=str(record["source_digest"]),
            page_number=int(record["page"]),
            threshold=int(record["threshold"]),
            column=int(record["column"]),
            upper_row=int(record["upper_row"]),
        )
        stored = copy.deepcopy(record)
        stored["algorithm_version"] = BOUNDARY_ALGORITHM_VERSION
        stored["geometry_compat_version"] = GEOMETRY_COMPAT_VERSION
        with self._lock:
            self._records[key] = stored
            self._write_locked()

    def page_records(
        self,
        *,
        source_digest: str,
        page_number: int,
        threshold: int,
    ) -> list[dict]:
        self._load()
        prefix = ":".join(
            [
                f"algo{BOUNDARY_ALGORITHM_VERSION}",
                f"geom{GEOMETRY_COMPAT_VERSION}",
                source_digest,
                f"p{int(page_number)}",
                f"t{int(threshold)}",
            ]
        ) + ":"
        with self._lock:
            return [
                copy.deepcopy(value)
                for key, value in self._records.items()
                if key.startswith(prefix)
            ]

    def _write_locked(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "format": "saol-row-boundary-corrections",
            "version": 1,
            "records": self._records,
        }
        tmp = self.path.with_name(self.path.name + f".tmp-{os.getpid()}-{threading.get_ident()}")
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(tmp, self.path)


def apply_boundary_corrections(row_map: dict, records: Iterable[dict]) -> dict:
    """Return a copied row map with cached straight horizontal cuts applied."""
    result = copy.deepcopy(row_map)
    columns = result.get("columns") or []
    for record in records:
        column = int(record["column"])
        upper_row = int(record["upper_row"])
        boundary = int(record["corrected_boundary"])
        if not 0 <= column < len(columns):
            continue
        rows = columns[column].get("rows") or []
        if not 0 <= upper_row < len(rows) - 1:
            continue
        upper = rows[upper_row]
        lower = rows[upper_row + 1]
        upper_top = int(upper["page_top"])
        lower_bottom = int(lower["page_bottom"])
        if not upper_top < boundary < lower_bottom:
            continue
        upper["page_bottom"] = boundary
        lower["page_top"] = boundary
        # Keep center_y useful for diagnostics/sorting without changing row index.
        upper["center_y"] = (int(upper["page_top"]) + int(upper["page_bottom"]) - 1) / 2.0
        lower["center_y"] = (int(lower["page_top"]) + int(lower["page_bottom"]) - 1) / 2.0
    return result


def _column_x_bounds(page_image: Image.Image, column_entry: dict, upper: dict, lower: dict) -> tuple[int, int]:
    lefts = [int(value) for value in (column_entry.get("left"), upper.get("crop_left"), lower.get("crop_left")) if value is not None]
    rights = [int(value) for value in (column_entry.get("right"), upper.get("crop_right"), lower.get("crop_right")) if value is not None]
    left = max(0, min(lefts) if lefts else 0)
    right = min(page_image.width, max(rights) if rights else page_image.width)
    if right <= left:
        left, right = 0, page_image.width
    return left, right


def _analyse_strict_row(
    page_image: Image.Image,
    *,
    left: int,
    right: int,
    top: int,
    bottom: int,
    models: list[GlyphModel],
    threshold: int,
) -> dict:
    crop = page_image.crop((left, top, right, bottom)).convert("L")
    result = analyse_row_exact_grouped_with_baseline_fallback(crop, models, threshold=threshold)
    source = int(result.get("source_pixels") or 0)
    covered = int(result.get("covered_pixels") or 0)
    return {
        "source": source,
        "covered": covered,
        "unmatched": source - covered,
        "fully_exact": bool(result.get("fully_exact")),
        "baseline": result.get("baseline"),
    }


def evaluate_boundary(
    page_image: Image.Image,
    row_map: dict,
    column: int,
    upper_row: int,
    boundary: int,
    models: Iterable[GlyphModel],
    *,
    threshold: int = 210,
) -> dict:
    """Score one straight cut while keeping every source pixel on exactly one side."""
    model_rows = list(models)
    column_entry = (row_map.get("columns") or [])[column]
    rows = column_entry.get("rows") or []
    upper = rows[upper_row]
    lower = rows[upper_row + 1]
    upper_top = int(upper["page_top"])
    lower_bottom = int(lower["page_bottom"])
    if not upper_top < boundary < lower_bottom:
        raise ValueError("boundary must lie strictly between outer row limits")
    left, right = _column_x_bounds(page_image, column_entry, upper, lower)
    upper_result = _analyse_strict_row(
        page_image,
        left=left,
        right=right,
        top=upper_top,
        bottom=boundary,
        models=model_rows,
        threshold=threshold,
    )
    lower_result = _analyse_strict_row(
        page_image,
        left=left,
        right=right,
        top=boundary,
        bottom=lower_bottom,
        models=model_rows,
        threshold=threshold,
    )
    return {
        "boundary": int(boundary),
        "upper": upper_result,
        "lower": lower_result,
        "unmatched": upper_result["unmatched"] + lower_result["unmatched"],
        "covered": upper_result["covered"] + lower_result["covered"],
        "source": upper_result["source"] + lower_result["source"],
    }


def find_boundary_correction(
    page_image: Image.Image,
    row_map: dict,
    column: int,
    upper_row: int,
    models: Iterable[GlyphModel],
    *,
    threshold: int = 210,
    max_shift: int = 4,
    source_digest_value: str | None = None,
    page_number: int | None = None,
) -> dict | None:
    """Find a conservative glyph-proven horizontal correction for two rows.

    The existing segmentation stays authoritative unless moving the cut by at
    most ``max_shift`` pixels strictly reduces the combined unexplained ink and
    does not increase unexplained ink on either row. If several moved cuts tie
    for the best result, the evidence is ambiguous and no correction is made.
    """
    model_rows = list(models)
    columns = row_map.get("columns") or []
    if not 0 <= column < len(columns):
        return None
    rows = columns[column].get("rows") or []
    if not 0 <= upper_row < len(rows) - 1:
        return None
    upper = rows[upper_row]
    lower = rows[upper_row + 1]
    old_upper_bottom = int(upper["page_bottom"])
    old_lower_top = int(lower["page_top"])
    # Adjacent physical rows normally share one cut. In the rare case of a gap
    # or overlap, search around their midpoint but retain both values in diagnostics.
    original = int(round((old_upper_bottom + old_lower_top) / 2.0))
    outer_top = int(upper["page_top"])
    outer_bottom = int(lower["page_bottom"])

    candidates = []
    for boundary in range(original - int(max_shift), original + int(max_shift) + 1):
        if not outer_top < boundary < outer_bottom:
            continue
        candidates.append(
            evaluate_boundary(
                page_image,
                row_map,
                column,
                upper_row,
                boundary,
                model_rows,
                threshold=threshold,
            )
        )
    if not candidates:
        return None
    by_boundary = {item["boundary"]: item for item in candidates}
    baseline = by_boundary.get(original)
    if baseline is None:
        return None

    moved = [item for item in candidates if item["boundary"] != original]
    acceptable = [
        item
        for item in moved
        if item["unmatched"] < baseline["unmatched"]
        and item["upper"]["unmatched"] <= baseline["upper"]["unmatched"]
        and item["lower"]["unmatched"] <= baseline["lower"]["unmatched"]
    ]
    if not acceptable:
        return None

    best_unmatched = min(item["unmatched"] for item in acceptable)
    best = [item for item in acceptable if item["unmatched"] == best_unmatched]
    # A straight cut is only learned when glyph evidence identifies one cut.
    if len(best) != 1:
        return None
    winner = best[0]

    return {
        "status": "accepted-glyph-proven-horizontal-boundary",
        "page": int(page_number or 0),
        "column": int(column),
        "upper_row": int(upper_row),
        "lower_row": int(upper_row) + 1,
        "threshold": int(threshold),
        "source_digest": source_digest_value or page_digest(page_image),
        "original_upper_bottom": old_upper_bottom,
        "original_lower_top": old_lower_top,
        "original_boundary": original,
        "corrected_boundary": int(winner["boundary"]),
        "shift": int(winner["boundary"] - original),
        "max_shift": int(max_shift),
        "before": {
            "unmatched": baseline["unmatched"],
            "covered": baseline["covered"],
            "upper_unmatched": baseline["upper"]["unmatched"],
            "lower_unmatched": baseline["lower"]["unmatched"],
        },
        "after": {
            "unmatched": winner["unmatched"],
            "covered": winner["covered"],
            "upper_unmatched": winner["upper"]["unmatched"],
            "lower_unmatched": winner["lower"]["unmatched"],
        },
        "evidence_facit_digest": model_digest(model_rows),
    }
