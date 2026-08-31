from __future__ import annotations

import io
import json
import subprocess
import tempfile
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
            raise RuntimeError(
                "tesseract failed: " + (proc.stderr.strip() or f"exit status {proc.returncode}")
            )
        return [word for word in read_words(io.StringIO(proc.stdout)) if word.text.strip()]


def _row_crop_box(
    row: dict[str, Any],
    *,
    column: int,
    page_width: int,
    page_height: int,
    pad_y: int = 1,
) -> tuple[int, int, int, int]:
    left, right = _column_bounds(column, page_width)
    top = max(0, int(row["page_top"]) - max(0, int(pad_y)))
    bottom = min(page_height, int(row["page_bottom"]) + max(0, int(pad_y)))
    return left, top, right, bottom


def ocr_page_row_map(
    page_image: Image.Image,
    row_map: dict[str, Any],
    *,
    lang: str = "swe",
    psm: int = 7,
    pad_y: int = 1,
) -> list[dict[str, Any]]:
    """OCR every physical row in row-map reading order.

    The row map, rather than Tesseract's page segmentation, owns the geometry.
    Tesseract is used only as a recognizer inside each already identified row.
    """
    records: list[dict[str, Any]] = []
    for column_entry in sorted(row_map.get("columns") or [], key=lambda item: int(item["column"])):
        column = int(column_entry["column"])
        for row in sorted(
            column_entry.get("rows") or [],
            key=lambda item: (float(item["center_y"]), int(item["page_top"])),
        ):
            box = _row_crop_box(
                row,
                column=column,
                page_width=page_image.width,
                page_height=page_image.height,
                pad_y=pad_y,
            )
            x0, y0, x1, y1 = box
            crop = page_image.crop(box).convert("L")
            words = _run_row_tesseract(crop, lang=lang, psm=psm)
            for word in sorted(words, key=lambda item: (item.left, item.word)):
                records.append(
                    {
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
                    }
                )
    return records


def add_jsonl_hints(
    records: list[dict[str, Any]],
    jsonl: Path,
    page_number: int,
) -> list[dict[str, Any]]:
    rows = [row for row in read_jsonl(jsonl) if _page_from_row(row) == page_number]
    refs = reference_tokens(rows, text_limit=50)
    hints = align_ocr_words([str(record.get("text") or "") for record in records], refs)
    for record, hint in zip(records, hints):
        record["jsonl_hint"] = hint
    return records


def write_row_map_ocr(
    page_image: Image.Image,
    row_map: dict[str, Any],
    jsonl: Path,
    page_number: int,
    destination: Path,
    *,
    lang: str = "swe",
    psm: int = 7,
    pad_y: int = 1,
) -> list[dict[str, Any]]:
    records = ocr_page_row_map(page_image, row_map, lang=lang, psm=psm, pad_y=pad_y)
    add_jsonl_hints(records, jsonl, page_number)
    payload = {
        "format": "saol-page-row-ocr-v1",
        "page": page_number,
        "row_count": int(row_map.get("row_count") or 0),
        "word_count": len(records),
        "lattice_word_count": sum(
            1 for record in records if record.get("row_source") == "white-gap-ink-island"
        ),
        "words": records,
    }
    destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return records


def write_lattice_debug_files(
    page_image: Image.Image,
    records: list[dict[str, Any]],
    out_dir: Path,
    *,
    page_number: int,
    source: str,
    threshold: int = 210,
) -> int:
    """Feed newly discovered lattice rows into the existing glyph pipeline.

    Existing Tesseract rows continue through the old preparation path during the
    migration. Only rows that page segmentation completely missed are added
    here, so there are no duplicate review entries.
    """
    png_dir = out_dir / "png"
    png_dir.mkdir(exist_ok=True)
    lattice = [
        record
        for record in records
        if record.get("row_source") == "white-gap-ink-island"
        and isinstance(record.get("jsonl_hint"), dict)
    ]
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
            "physical_row": {
                "source": "white-gap-ink-island",
                "column": int(record["column"]),
                "row_index": int(record["row_index"]),
                "page_top": int(record["row_page_top"]),
                "page_bottom": int(record["row_page_bottom"]),
                "center_y": float(record["row_center_y"]),
            },
            "jsonl_hint": record["jsonl_hint"],
            "tesseract": {
                "mode": "row-map-psm7",
                "text": str(record["text"]),
                "confidence": record.get("confidence"),
                "raw_bbox": [bx, by, bw, bh],
            },
        }
        (out_dir / f"{stem}.json").write_text(
            json.dumps(debug, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        written += 1
    return written
