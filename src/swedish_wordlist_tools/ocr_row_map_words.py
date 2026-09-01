from __future__ import annotations

import io
import json
import subprocess
import tempfile
from collections import deque
from pathlib import Path
from typing import Any

from PIL import Image

from .ocr_jsonl_page_hints import align_ocr_words, reference_tokens
from .ocr_prepare_sequential_page import _black_pixels, _column_bounds, _page_from_row, read_jsonl
from .ocr_tsv_articles import OcrWord, read_words


def _run_row_tesseract(image: Image.Image, *, lang: str = "swe", psm: int = 7) -> list[OcrWord]:
    with tempfile.TemporaryDirectory(prefix="saol-row-map-") as td:
        image_path = Path(td) / "row.png"
        image.save(image_path)
        cmd = ["tesseract", str(image_path), "stdout", "-l", lang, "--psm", str(psm), "tsv"]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        if proc.returncode != 0:
            raise RuntimeError("tesseract failed: " + (proc.stderr.strip() or f"exit status {proc.returncode}"))
        return [word for word in read_words(io.StringIO(proc.stdout)) if word.text.strip()]


def _persistent_left_rule_x(
    page_image: Image.Image,
    column_entry: dict[str, Any],
    *,
    threshold: int = 210,
) -> int | None:
    """Find a vertical print rule near the left side of a column.

    A real rule is dark through most row-height samples. Aligned first letters
    are not, so measuring coverage over all retained row pixels separates the
    two without OCR knowledge.
    """
    rows = list(column_entry.get("rows") or [])
    if len(rows) < 8:
        return None
    left = int(column_entry.get("left") or 0)
    right = int(column_entry.get("right") or page_image.width)
    search_right = min(right, left + max(8, (right - left) // 3))
    gray = page_image.convert("L")
    pixels = gray.load()
    ys = [
        y
        for row in rows
        for y in range(max(0, int(row["page_top"])), min(gray.height, int(row["page_bottom"])))
    ]
    if not ys:
        return None
    candidates: list[tuple[float, int]] = []
    for x in range(max(0, left), max(0, search_right)):
        coverage = sum(1 for y in ys if pixels[x, y] < threshold) / len(ys)
        if coverage >= 0.72:
            candidates.append((coverage, x))
    if not candidates:
        return None
    _, x = max(candidates, key=lambda item: (item[0], -item[1]))
    return x


def _row_crop_box(
    row: dict[str, Any],
    *,
    column: int,
    page_width: int,
    page_height: int,
    pad_y: int = 1,
    left_override: int | None = None,
) -> tuple[int, int, int, int]:
    fallback_left, fallback_right = _column_bounds(column, page_width)
    left = int(row.get("crop_left", fallback_left))
    right = int(row.get("crop_right", fallback_right))
    left = max(0, min(page_width - 1, left))
    right = max(left + 1, min(page_width, right))
    if left_override is not None:
        left = max(left, min(right - 1, int(left_override)))
    top = max(0, int(row["page_top"]) - max(0, int(pad_y)))
    bottom = min(page_height, int(row["page_bottom"]) + max(0, int(pad_y)))
    return left, top, right, bottom


def _owned_row_crop(
    page_image: Image.Image,
    row: dict[str, Any],
    box: tuple[int, int, int, int],
    *,
    threshold: int = 210,
    probe_y: int = 6,
) -> tuple[Image.Image, int]:
    """Return a row crop with provably neighbor-owned edge ink removed.

    The ordinary crop deliberately includes a small vertical pad so glyphs that
    cross a segmentation edge can still be reconstructed. That pad can also
    contain a descender/ascender from the row above or below. We resolve only
    the cheap, unambiguous case: an ink component visible in the crop has no
    pixels inside the target row's own vertical span and is 8-connected to ink
    beyond the crop on the same side. Such pixels demonstrably belong to a
    neighbour, so they are whitened before glyph matching.

    Components that touch the target row proper are left untouched. This makes
    the filter deliberately conservative and symmetric for contamination from
    above and below.
    """
    x0, y0, x1, y1 = map(int, box)
    crop = page_image.crop(box).convert("L")
    if probe_y <= 0 or crop.width <= 0 or crop.height <= 0:
        return crop, 0

    core_top = max(y0, min(y1, int(row["page_top"])))
    core_bottom = max(core_top, min(y1, int(row["page_bottom"])))
    probe_top = max(0, y0 - int(probe_y))
    probe_bottom = min(page_image.height, y1 + int(probe_y))
    if probe_top == y0 and probe_bottom == y1:
        return crop, 0

    region = page_image.crop((x0, probe_top, x1, probe_bottom)).convert("L")
    pixels = region.load()
    remaining = {
        (x, y)
        for y in range(region.height)
        for x in range(region.width)
        if pixels[x, y] < threshold
    }
    if not remaining:
        return crop, 0

    crop_top = y0 - probe_top
    crop_bottom = y1 - probe_top
    local_core_top = core_top - probe_top
    local_core_bottom = core_bottom - probe_top
    foreign: set[tuple[int, int]] = set()

    while remaining:
        start = remaining.pop()
        queue = deque([start])
        component = {start}
        while queue:
            x, y = queue.popleft()
            for ny in range(y - 1, y + 2):
                for nx in range(x - 1, x + 2):
                    point = (nx, ny)
                    if point in remaining:
                        remaining.remove(point)
                        component.add(point)
                        queue.append(point)

        in_crop = {point for point in component if crop_top <= point[1] < crop_bottom}
        if not in_crop:
            continue
        in_core = {
            point for point in component
            if local_core_top <= point[1] < local_core_bottom
        }
        if in_core:
            continue
        continues_outside = any(point[1] < crop_top or point[1] >= crop_bottom for point in component)
        if continues_outside:
            foreign.update(in_crop)

    if not foreign:
        return crop, 0

    cleaned = crop.copy()
    cleaned_pixels = cleaned.load()
    for x, region_y in foreign:
        crop_y = region_y - crop_top
        if 0 <= x < cleaned.width and 0 <= crop_y < cleaned.height:
            cleaned_pixels[x, crop_y] = 255
    return cleaned, len(foreign)


def ocr_page_row_map(
    page_image: Image.Image,
    row_map: dict[str, Any],
    *,
    lang: str = "swe",
    psm: int = 7,
    pad_y: int = 1,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for column_entry in sorted(row_map.get("columns") or [], key=lambda item: int(item["column"])):
        column = int(column_entry["column"])
        rule_x = _persistent_left_rule_x(page_image, column_entry)
        content_left = rule_x + 2 if rule_x is not None else None
        column_entry["persistent_left_rule_x"] = rule_x
        column_entry["ocr_content_left"] = content_left
        for row in sorted(column_entry.get("rows") or [], key=lambda item: (float(item["center_y"]), int(item["page_top"]))):
            box = _row_crop_box(row, column=column, page_width=page_image.width, page_height=page_image.height, pad_y=pad_y, left_override=content_left)
            x0, y0, x1, y1 = box
            crop, _removed = _owned_row_crop(page_image, row, box)
            words = _run_row_tesseract(crop, lang=lang, psm=psm)
            for word in sorted(words, key=lambda item: (item.left, item.word)):
                records.append({
                    "column": column,
                    "row_index": int(row.get("index", 0)),
                    "row_source": str(row.get("source") or "unknown"),
                    "row_page_top": int(row["page_top"]),
                    "row_page_bottom": int(row["page_bottom"]),
                    "row_center_y": float(row["center_y"]),
                    "row_crop_box": [x0, y0, x1, y1],
                    "text": word.text,
                    "confidence": word.confidence,
                    "bbox": [x0 + word.left, y0 + word.top, word.width, word.height],
                    "bbox_in_row": [word.left, word.top, word.width, word.height],
                })
    return records


def add_jsonl_hints(records: list[dict[str, Any]], jsonl: Path, page_number: int) -> list[dict[str, Any]]:
    rows = [row for row in read_jsonl(jsonl) if _page_from_row(row) == page_number]
    refs = reference_tokens(rows, text_limit=50)
    hints = align_ocr_words([str(record.get("text") or "") for record in records], refs)
    for record, hint in zip(records, hints):
        record["jsonl_hint"] = hint
    return records


def write_row_map_ocr(page_image: Image.Image, row_map: dict[str, Any], jsonl: Path, page_number: int, destination: Path, *, lang: str = "swe", psm: int = 7, pad_y: int = 1) -> list[dict[str, Any]]:
    records = ocr_page_row_map(page_image, row_map, lang=lang, psm=psm, pad_y=pad_y)
    add_jsonl_hints(records, jsonl, page_number)
    payload = {
        "format": "saol-page-row-ocr-v1",
        "page": page_number,
        "row_count": int(row_map.get("row_count") or 0),
        "word_count": len(records),
        "lattice_word_count": sum(1 for record in records if record.get("row_source") == "white-gap-ink-island"),
        "words": records,
    }
    destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return records


def write_lattice_debug_files(page_image: Image.Image, records: list[dict[str, Any]], out_dir: Path, *, page_number: int, source: str, threshold: int = 210) -> int:
    png_dir = out_dir / "png"
    png_dir.mkdir(exist_ok=True)
    lattice = [record for record in records if record.get("row_source") == "white-gap-ink-island" and isinstance(record.get("jsonl_hint"), dict)]
    written = 0
    for index, record in enumerate(lattice):
        x0, y0, x1, y1 = map(int, record["row_crop_box"])
        crop = page_image.crop((x0, y0, x1, y1)).convert("L")
        ink = _black_pixels(crop, threshold)
        if not ink:
            continue
        stem = f"saol14-word-debug-p{page_number:05d}-rowmap-{index:04d}"
        crop.save(png_dir / f"{stem}.png")
        bx, by, bw, bh = map(int, record["bbox"])
        debug = {
            "format": "saol14-word-debug-v1",
            "expected_word": str(record["text"]),
            "headword": str(record["text"]),
            "page": page_number,
            "subnr": f"rowmap-{record['column']}-{record['row_index']}-{index}",
            "style": "unknown",
            "width": crop.width,
            "height": crop.height,
            "black_pixels": ink,
            "source_id": f"page:{page_number}:rowmap:{record['column']}:{record['row_index']}:{index}",
            "word_file": f"png/{stem}.png",
            "page_source": source,
            "page_word_bbox": [x0, y0, x1 - x0, y1 - y0],
            "target_word_bbox_in_crop": [bx - x0, by - y0, bw, bh],
            "five_row_context": None,
            "physical_row": {"source": "white-gap-ink-island", "column": int(record["column"]), "row_index": int(record["row_index"]), "page_top": int(record["row_page_top"]), "page_bottom": int(record["row_page_bottom"]), "center_y": float(record["row_center_y"])},
            "jsonl_hint": record["jsonl_hint"],
            "tesseract": {"mode": "row-map-psm7", "text": str(record["text"]), "confidence": record.get("confidence"), "raw_bbox": [bx, by, bw, bh]},
        }
        (out_dir / f"{stem}.json").write_text(json.dumps(debug, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written += 1
    return written
