from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image

from .ocr_prepare_sequential_page import _load_source_image
from .ocr_row_lattice import row_lattice_for_column


def _column_bounds(index: int, width: int, count: int) -> tuple[int, int]:
    left = index * width // count
    right = (index + 1) * width // count if index + 1 < count else width
    return left, right


def _run_line_tesseract(
    crop: Image.Image,
    *,
    lang: str = "swe",
    psm: int = 7,
) -> tuple[str, str]:
    """Run Tesseract on one already-segmented physical row."""
    with tempfile.TemporaryDirectory(prefix="saol-missing-row-") as td:
        image_path = Path(td) / "row.png"
        crop.save(image_path)
        cmd = [
            "tesseract",
            str(image_path),
            "stdout",
            "-l",
            lang,
            "--psm",
            str(psm),
        ]
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                "tesseract failed: "
                + (proc.stderr.strip() or f"exit status {proc.returncode}")
            )
        return proc.stdout.strip(), proc.stderr.strip()


def probe_missing_rows(
    out_dir: Path,
    *,
    threshold: int = 210,
    lang: str = "swe",
    psm: int = 7,
    pad_x: int = 3,
    pad_y: int = 1,
) -> list[dict[str, Any]]:
    """Find lattice-proposed rows and OCR each one as an isolated text line."""
    report_path = out_dir / "page-report.json"
    row_map_path = out_dir / "page-row-map.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    row_map = json.loads(row_map_path.read_text(encoding="utf-8"))

    source = str(report.get("source") or "")
    if not source:
        raise RuntimeError(f"missing source in {report_path}")
    page = _load_source_image(source)
    if page is None:
        raise RuntimeError(f"could not load page image: {source}")
    page = page.convert("L")

    columns = list(row_map.get("columns") or [])
    results: list[dict[str, Any]] = []
    for column_index, column in enumerate(columns):
        left, right = _column_bounds(column_index, page.width, len(columns))
        lattice = row_lattice_for_column(
            page,
            list(column.get("rows") or []),
            left=left,
            right=right,
            threshold=threshold,
        )
        for proposed in lattice.get("proposed_rows") or []:
            ink_left = int(proposed["ink_left"])
            ink_right = int(proposed["ink_right"])
            top = int(proposed["page_top"])
            bottom = int(proposed["page_bottom"])
            box = (
                max(left, ink_left - pad_x),
                max(0, top - pad_y),
                min(right, ink_right + pad_x),
                min(page.height, bottom + pad_y),
            )
            crop = page.crop(box)
            text, stderr = _run_line_tesseract(crop, lang=lang, psm=psm)
            item = {
                "column": column_index,
                "source": proposed.get("source"),
                "page_top": top,
                "page_bottom": bottom,
                "center_y": proposed.get("center_y"),
                "ink_bbox": proposed.get("ink_bbox"),
                "ocr_box": list(box),
                "ocr_text": text,
            }
            if stderr:
                item["tesseract_stderr"] = stderr
            results.append(item)
    return results


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "OCR lattice-proposed Tesseract-missed physical rows as isolated lines."
        )
    )
    ap.add_argument("out_dir", type=Path)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--lang", default="swe")
    ap.add_argument("--psm", type=int, default=7)
    ap.add_argument("--pad-x", type=int, default=3)
    ap.add_argument("--pad-y", type=int, default=1)
    args = ap.parse_args()

    results = probe_missing_rows(
        args.out_dir,
        threshold=args.threshold,
        lang=args.lang,
        psm=args.psm,
        pad_x=args.pad_x,
        pad_y=args.pad_y,
    )
    print(f"proposed_rows={len(results)}")
    for item in results:
        print(json.dumps(item, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
