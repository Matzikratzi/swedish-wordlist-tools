from __future__ import annotations

import argparse
import io
import json
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Iterable

from PIL import Image

from .ocr_prepare_next20_glyph_words import _load_page_image
from .ocr_tsv_articles import OcrWord, read_words

PAGE_RE = re.compile(r"SAOL14_(\d{5})\.png", re.I)
DEBUG_FORMAT = "saol14-word-debug-v1"


def _page_from_row(row: dict[str, Any]) -> int | None:
    src = str(row.get("source") or "")
    m = PAGE_RE.search(src)
    if m:
        return int(m.group(1))
    for key in ("sidnr1", "sidnr2", "page", "page_number", "sidnr"):
        value = row.get(key)
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            pass
    return None


def read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{lineno}: invalid JSON: {exc}") from exc
            if isinstance(row, dict):
                yield row


def source_for_page(rows: Iterable[dict[str, Any]], page: int) -> str | None:
    fallback: str | None = None
    for row in rows:
        src = str(row.get("source") or "")
        if not src:
            continue
        m = PAGE_RE.search(src)
        if m and int(m.group(1)) == page:
            return src
        if _page_from_row(row) == page and fallback is None:
            fallback = src
    return fallback


def _black_pixels(im: Image.Image, threshold: int) -> list[list[int]]:
    gray = im.convert("L")
    return [
        [x, y]
        for y in range(gray.height)
        for x in range(gray.width)
        if gray.getpixel((x, y)) < threshold
    ]


def _run_tesseract(page_image: Image.Image, *, lang: str, psm: int) -> list[OcrWord]:
    with tempfile.TemporaryDirectory(prefix="saol-page-") as td:
        image_path = Path(td) / "page.png"
        page_image.save(image_path)
        cmd = ["tesseract", str(image_path), "stdout", "-l", lang, "--psm", str(psm), "tsv"]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        if proc.returncode != 0:
            raise RuntimeError(
                "tesseract failed: " + (proc.stderr.strip() or f"exit status {proc.returncode}")
            )
        return read_words(io.StringIO(proc.stdout))


def _load_source_image(source: str) -> Image.Image | None:
    local = Path(source)
    if local.exists():
        return _load_page_image({"page_image": str(local)})
    return _load_page_image({"source": source})


def _crop_box(word: OcrWord, page: Image.Image, pad_x: int, pad_y: int) -> tuple[int, int, int, int]:
    x0 = max(0, word.left - pad_x)
    y0 = max(0, word.top - pad_y)
    x1 = min(page.width, word.left + word.width + pad_x)
    y1 = min(page.height, word.top + word.height + pad_y)
    return x0, y0, x1, y1


def prepare_page(
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
) -> dict[str, Any]:
    source = source_for_page(read_jsonl(jsonl), page_number)
    if not source:
        raise LookupError(f"no source found for page {page_number}")

    page_image = _load_source_image(source)
    if page_image is None:
        raise RuntimeError(f"could not load page image: {source}")

    words = _run_tesseract(page_image, lang=lang, psm=psm)
    words = [w for w in words if w.text.strip() and w.confidence >= min_confidence]
    words.sort(key=lambda w: (w.top, w.left, w.block, w.paragraph, w.line, w.word))

    out_dir.mkdir(parents=True, exist_ok=True)
    png_dir = out_dir / "png"
    png_dir.mkdir(exist_ok=True)

    written = 0
    skipped_blank = 0
    for i, word in enumerate(words):
        x0, y0, x1, y1 = _crop_box(word, page_image, pad_x, pad_y)
        crop = page_image.crop((x0, y0, x1, y1)).convert("L")
        ink = _black_pixels(crop, threshold)
        if not ink:
            skipped_blank += 1
            continue

        stem = f"saol14-word-debug-p{page_number:05d}-{i:04d}"
        crop.save(png_dir / f"{stem}.png")
        debug = {
            "format": DEBUG_FORMAT,
            "expected_word": word.text,
            "headword": word.text,
            "page": page_number,
            "subnr": f"ocr-{word.block}-{word.paragraph}-{word.line}-{word.word}",
            "style": "unknown",
            "width": crop.width,
            "height": crop.height,
            "black_pixels": ink,
            "source_id": f"page:{page_number}:ocr:{word.block}:{word.paragraph}:{word.line}:{word.word}",
            "word_file": f"png/{stem}.png",
            "page_source": source,
            "page_word_bbox": [x0, y0, x1 - x0, y1 - y0],
            "tesseract": {
                "text": word.text,
                "confidence": word.confidence,
                "block": word.block,
                "paragraph": word.paragraph,
                "line": word.line,
                "word": word.word,
                "raw_bbox": [word.left, word.top, word.width, word.height],
            },
        }
        (out_dir / f"{stem}.json").write_text(
            json.dumps(debug, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        written += 1

    report = {
        "format": "saol14-sequential-page-preparation-v1",
        "jsonl": str(jsonl),
        "page": page_number,
        "source": source,
        "page_size": [page_image.width, page_image.height],
        "tesseract_words": len(words),
        "word_debug_files": written,
        "skipped_blank": skipped_blank,
        "out_dir": str(out_dir),
    }
    (out_dir / "page-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Prepare one SAOL facsimile page, in reading order, for exact glyph review."
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--page", type=int, required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--lang", default="swe")
    ap.add_argument("--psm", type=int, default=4)
    ap.add_argument("--pad-x", type=int, default=1)
    ap.add_argument("--pad-y", type=int, default=5)
    ap.add_argument("--min-confidence", type=float, default=-1.0)
    args = ap.parse_args()

    report = prepare_page(
        args.jsonl,
        args.page,
        args.out_dir,
        threshold=args.threshold,
        lang=args.lang,
        psm=args.psm,
        pad_x=args.pad_x,
        pad_y=args.pad_y,
        min_confidence=args.min_confidence,
    )
    print(f"page={report['page']}")
    print(f"source={report['source']}")
    print(f"page_size={report['page_size'][0]}x{report['page_size'][1]}")
    print(f"tesseract_words={report['tesseract_words']}")
    print(f"word_debug_files={report['word_debug_files']}")
    print(args.out_dir)
    return 0 if report["word_debug_files"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
