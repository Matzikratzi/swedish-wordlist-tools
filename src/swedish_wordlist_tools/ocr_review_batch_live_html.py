from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import ocr_review_batch_defects_html as batch
from .ocr_batch_progress_cache import BatchProgressStore, DEFAULT_CACHE_PATH
from .ocr_review_batch_prefetch import BatchPrefetcher


def _live_args(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--pages", required=True)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--facit", type=Path, default=Path("glyphs/saol14-manual-glyph-facit.json"))
    ap.add_argument("--progress-cache", type=Path, default=DEFAULT_CACHE_PATH)
    args, _unknown = ap.parse_known_args(argv[1:])
    return args


def main() -> int:
    live = _live_args(sys.argv)
    pages = batch.parse_pages(live.pages)
    original_launch_editor = batch.launch_editor

    def launch_with_prefetch(
        jsonl: Path,
        *,
        page: int,
        position: tuple[int, int],
        threshold: int,
        facit: Path,
        host: str,
        port: int,
        no_browser: bool,
    ) -> int:
        later_pages = [candidate for candidate in pages if candidate > page]
        prefetcher = BatchPrefetcher(
            jsonl=jsonl,
            pages=later_pages,
            threshold=threshold,
            facit=facit,
            progress_store=BatchProgressStore(live.progress_cache),
        )
        prefetcher.start()
        try:
            return original_launch_editor(
                jsonl,
                page=page,
                position=position,
                threshold=threshold,
                facit=facit,
                host=host,
                port=port,
                no_browser=no_browser,
            )
        finally:
            prefetcher.stop()

    batch.launch_editor = launch_with_prefetch
    try:
        return batch.main()
    finally:
        batch.launch_editor = original_launch_editor


if __name__ == "__main__":
    raise SystemExit(main())
