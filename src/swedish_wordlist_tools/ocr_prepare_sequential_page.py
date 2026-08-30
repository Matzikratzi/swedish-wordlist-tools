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

from .ocr_jsonl_page_hints import align_ocr_words, reference_tokens
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


def _components(ink: set[tuple[int, int]]) -> list[set[tuple[int, int]]]:
    remaining = set(ink)
    out: list[set[tuple[int, int]]] = []
    while remaining:
        seed = remaining.pop()
        stack = [seed]
        comp = {seed}
        while stack:
            x, y = stack.pop()
            for point in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if point in remaining:
                    remaining.remove(point)
                    comp.add(point)
                    stack.append(point)
        out.append(comp)
    return out


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


def _column_index(word: OcrWord, page_width: int) -> int:
    center = word.left + word.width / 2
    return max(0, min(2, int((3 * center) / max(1, page_width))))


def _column_bounds(column: int, page_width: int) -> tuple[int, int]:
    return (column * page_width // 3, (column + 1) * page_width // 3)


def _line_key(word: OcrWord, page_width: int) -> tuple[int, int, int, int]:
    return (_column_index(word, page_width), word.block, word.paragraph, word.line)


def _physical_lines(words: list[OcrWord], page_width: int) -> dict[tuple[int, int, int, int], dict[str, Any]]:
    grouped: dict[tuple[int, int, int, int], list[OcrWord]] = {}
    for word in words:
        grouped.setdefault(_line_key(word, page_width), []).append(word)

    out: dict[tuple[int, int, int, int], dict[str, Any]] = {}
    by_col: dict[int, list[tuple[tuple[int, int, int, int], dict[str, Any]]]] = {}
    for key, line_words in grouped.items():
        top = min(w.top for w in line_words)
        bottom = max(w.top + w.height for w in line_words)
        item = {
            "key": list(key),
            "top": top,
            "bottom": bottom,
            "left": min(w.left for w in line_words),
            "right": max(w.left + w.width for w in line_words),
            "text": " ".join(w.text for w in sorted(line_words, key=lambda w: (w.left, w.word))),
        }
        by_col.setdefault(key[0], []).append((key, item))

    for col, rows in by_col.items():
        rows.sort(key=lambda pair: (pair[1]["top"], pair[1]["left"], pair[0][1:]))
        column_left, column_right = _column_bounds(col, page_width)
        for index, (key, item) in enumerate(rows):
            lo = max(0, index - 2)
            hi = min(len(rows), index + 3)
            context_rows = [dict(candidate) for _, candidate in rows[lo:hi]]
            out[key] = {
                "column": col,
                "column_left": column_left,
                "column_right": column_right,
                "target_index": index - lo,
                "bands_page": context_rows,
            }
    return out


def _nearest_row_index(y: int, bands: list[dict[str, Any]]) -> int:
    return min(
        range(len(bands)),
        key=lambda i: (
            abs(y - (float(bands[i]["top"]) + float(bands[i]["bottom"])) / 2.0),
            i,
        ),
    )


def _rows_share_black_component(
    page: Image.Image,
    bands: list[dict[str, Any]],
    left_index: int,
    right_index: int,
    column_left: int,
    column_right: int,
    threshold: int,
) -> bool:
    if not bands:
        return False
    y0 = max(0, min(int(b["top"]) for b in bands))
    y1 = min(page.height, max(int(b["bottom"]) for b in bands))
    crop = page.crop((column_left, y0, column_right, y1)).convert("L")
    ink = {
        (x + column_left, y + y0)
        for y in range(crop.height)
        for x in range(crop.width)
        if crop.getpixel((x, y)) < threshold
    }
    for comp in _components(ink):
        owners = {_nearest_row_index(y, bands) for _, y in comp}
        if left_index in owners and right_index in owners:
            return True
    return False


def _active_line_context(
    page: Image.Image,
    line_context: dict[str, Any] | None,
    threshold: int,
) -> dict[str, Any] | None:
    """Use target +/-1 rows normally and outer support rows only when needed.

    The source context keeps up to five physical rows. Analysis always includes
    the target row and its immediate neighbours. Row -2 or +2 is activated only
    when a 4-connected black component crosses between that outer row's Voronoi
    region and the nearer neighbour row. This lets a glyph tangle spill across
    rows without making remote rows free OCR search space.
    """
    if not line_context or not line_context.get("bands_page"):
        return line_context
    bands = list(line_context["bands_page"])
    target = int(line_context["target_index"])
    active = set(range(max(0, target - 1), min(len(bands), target + 2)))
    column_left = int(line_context.get("column_left", 0))
    column_right = int(line_context.get("column_right", page.width))

    upper_outer = target - 2
    if upper_outer >= 0 and _rows_share_black_component(
        page, bands, upper_outer, upper_outer + 1, column_left, column_right, threshold
    ):
        active.add(upper_outer)

    lower_outer = target + 2
    if lower_outer < len(bands) and _rows_share_black_component(
        page, bands, lower_outer - 1, lower_outer, column_left, column_right, threshold
    ):
        active.add(lower_outer)

    indices = sorted(active)
    selected = [dict(bands[i]) for i in indices]
    return {
        **line_context,
        "bands_page": selected,
        "target_index": indices.index(target),
        "source_band_indices": indices,
        "outer_support_rows": [i for i in indices if abs(i - target) == 2],
    }


def _crop_box(
    word: OcrWord,
    page: Image.Image,
    pad_x: int,
    pad_y: int,
    line_context: dict[str, Any] | None = None,
) -> tuple[int, int, int, int]:
    if line_context and line_context.get("bands_page"):
        bands = line_context["bands_page"]
        # Column boundaries are already the safe horizontal context boundary.
        # Do not pad across them into the neighbouring dictionary column.
        x0 = max(0, int(line_context.get("column_left", word.left)))
        x1 = min(page.width, int(line_context.get("column_right", word.left + word.width)))
        y0 = max(0, min(int(b["top"]) for b in bands) - pad_y)
        y1 = min(page.height, max(int(b["bottom"]) for b in bands) + pad_y)
    else:
        x0 = max(0, word.left - pad_x)
        x1 = min(page.width, word.left + word.width + pad_x)
        y0 = max(0, word.top - pad_y)
        y1 = min(page.height, word.top + word.height + pad_y)
    return x0, y0, x1, y1


def _relative_five_row_context(
    line_context: dict[str, Any] | None,
    crop_box: tuple[int, int, int, int],
) -> dict[str, Any] | None:
    if not line_context or not line_context.get("bands_page"):
        return None
    x0, y0, x1, y1 = crop_box
    bands = []
    for band in line_context["bands_page"]:
        bands.append(
            {
                "top": max(0, int(band["top"]) - y0),
                "bottom": min(y1 - y0, int(band["bottom"]) - y0),
                "page_top": int(band["top"]),
                "page_bottom": int(band["bottom"]),
                "text": str(band.get("text") or ""),
            }
        )
    return {
        "column": int(line_context["column"]),
        "target_index": int(line_context["target_index"]),
        "bands": bands,
        "source_band_indices": list(line_context.get("source_band_indices") or []),
        "outer_support_rows": list(line_context.get("outer_support_rows") or []),
    }


def _reading_order_key(word: OcrWord, page_width: int) -> tuple[int, int, int, int, int, int, int]:
    """Approximate SAOL's three-column reading order using page geometry."""
    col = _column_index(word, page_width)
    return (col, word.top, word.left, word.block, word.paragraph, word.line, word.word)


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
    all_rows = list(read_jsonl(jsonl))
    source = source_for_page(all_rows, page_number)
    if not source:
        raise LookupError(f"no source found for page {page_number}")

    page_rows = [row for row in all_rows if _page_from_row(row) == page_number]
    page_image = _load_source_image(source)
    if page_image is None:
        raise RuntimeError(f"could not load page image: {source}")

    words = _run_tesseract(page_image, lang=lang, psm=psm)
    words = [w for w in words if w.text.strip() and w.confidence >= min_confidence]
    line_contexts = _physical_lines(words, page_image.width)
    active_contexts = {
        key: _active_line_context(page_image, context, threshold)
        for key, context in line_contexts.items()
    }
    words.sort(key=lambda w: _reading_order_key(w, page_image.width))

    refs = reference_tokens(page_rows, text_limit=50)
    hints = align_ocr_words([w.text for w in words], refs) if refs else [None] * len(words)

    out_dir.mkdir(parents=True, exist_ok=True)
    png_dir = out_dir / "png"
    png_dir.mkdir(exist_ok=True)

    written = 0
    skipped_blank = 0
    hinted = 0
    five_row_words = 0
    outer_support_words = 0
    for i, (word, hint) in enumerate(zip(words, hints)):
        line_context = active_contexts.get(_line_key(word, page_image.width))
        box = _crop_box(word, page_image, pad_x, pad_y, line_context)
        x0, y0, x1, y1 = box
        crop = page_image.crop(box).convert("L")
        ink = _black_pixels(crop, threshold)
        if not ink:
            skipped_blank += 1
            continue

        five_row_context = _relative_five_row_context(line_context, box)
        if five_row_context:
            five_row_words += 1
            if five_row_context.get("outer_support_rows"):
                outer_support_words += 1

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
            "target_word_bbox_in_crop": [word.left - x0, word.top - y0, word.width, word.height],
            "five_row_context": five_row_context,
            "jsonl_hint": hint,
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
        if hint:
            hinted += 1
        (out_dir / f"{stem}.json").write_text(
            json.dumps(debug, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        written += 1

    report = {
        "format": "saol14-sequential-page-preparation-v4",
        "jsonl": str(jsonl),
        "page": page_number,
        "source": source,
        "page_size": [page_image.width, page_image.height],
        "jsonl_rows": len(page_rows),
        "jsonl_reference_tokens": len(refs),
        "tesseract_words": len(words),
        "hinted_words": hinted,
        "five_row_context_words": five_row_words,
        "outer_support_words": outer_support_words,
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
    print(f"jsonl_rows={report['jsonl_rows']}")
    print(f"jsonl_reference_tokens={report['jsonl_reference_tokens']}")
    print(f"tesseract_words={report['tesseract_words']}")
    print(f"hinted_words={report['hinted_words']}")
    print(f"five_row_context_words={report['five_row_context_words']}")
    print(f"outer_support_words={report['outer_support_words']}")
    print(f"word_debug_files={report['word_debug_files']}")
    print(args.out_dir)
    return 0 if report["word_debug_files"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
