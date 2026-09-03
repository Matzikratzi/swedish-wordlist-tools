from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .ocr_find_unreviewed_glyph_rows import QUEUE_FORMAT
from . import ocr_review_page_pixel_array_glyphs_html as editor


def load_queue_positions(path: Path, page: int) -> list[tuple[int, int]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("format") != QUEUE_FORMAT:
        raise ValueError(f"unsupported queue format: {payload.get('format')!r}")
    out: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()
    for item in payload.get("rows") or []:
        if int(item.get("page")) != int(page):
            continue
        position = (int(item.get("column")), int(item.get("row")))
        if position not in seen:
            out.append(position)
            seen.add(position)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Run the byte-array glyph editor on only rows saved in a review queue.")
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--queue", type=Path, required=True)
    ap.add_argument("--page", type=int, required=True)
    ap.add_argument("--facit", type=Path, required=True)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    queued = load_queue_positions(args.queue, args.page)
    if not queued:
        raise ValueError(f"queue contains no rows for page {args.page}")

    original_builder = editor.build_page_context_pixel_array

    def build_filtered_context(jsonl, page_number: int, threshold: int = 210):
        context = original_builder(jsonl, page_number, threshold)
        present = set(context["positions"])
        missing = [position for position in queued if position not in present]
        if missing:
            raise ValueError(f"queued rows are not present on page {page_number}: {missing}")
        context["positions"] = list(queued)
        print(
            f"review-queue: page {page_number}: visar endast {len(queued)} sparade rader",
            flush=True,
        )
        return context

    editor.build_page_context_pixel_array = build_filtered_context
    initial_column, initial_row = queued[0]
    argv = [
        sys.argv[0],
        str(args.jsonl),
        "--page", str(args.page),
        "--column", str(initial_column),
        "--row", str(initial_row),
        "--threshold", str(args.threshold),
        "--facit", str(args.facit),
        "--host", args.host,
        "--port", str(args.port),
    ]
    if args.no_browser:
        argv.append("--no-browser")
    sys.argv = argv
    return editor.main()


if __name__ == "__main__":
    raise SystemExit(main())
