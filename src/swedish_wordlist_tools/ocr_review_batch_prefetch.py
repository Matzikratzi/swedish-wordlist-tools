from __future__ import annotations

import threading
import time
from pathlib import Path

from .ocr_glyph_matcher import load_facit
from .ocr_review_batch_defects_html import scan_page


class BatchPrefetcher:
    """Scan later pages while the user is editing the current defect.

    Exact rows are safe to cache when the facit only grows.  If a later row is
    defective with the current facit, the worker waits for the facit file to
    change, reloads it, and retries that page instead of treating the stale
    defect as final.
    """

    def __init__(
        self,
        *,
        jsonl: Path,
        pages: list[int],
        threshold: int,
        facit: Path,
        progress_store,
        poll_seconds: float = 0.5,
        printer=print,
    ) -> None:
        self.jsonl = Path(jsonl)
        self.pages = list(pages)
        self.threshold = int(threshold)
        self.facit = Path(facit)
        self.progress_store = progress_store
        self.poll_seconds = float(poll_seconds)
        self.printer = printer
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if not self.pages or self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="ocr-batch-prefetch", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def _facit_stamp(self) -> tuple[int, int]:
        try:
            stat = self.facit.stat()
            return stat.st_mtime_ns, stat.st_size
        except FileNotFoundError:
            return (0, 0)

    def _wait_for_facit_change(self, stamp: tuple[int, int]) -> bool:
        while not self._stop.wait(self.poll_seconds):
            if self._facit_stamp() != stamp:
                return True
        return False

    def _run(self) -> None:
        self.printer(
            f"batch-prefetch: fortsätter i bakgrunden med sidor {self.pages}",
            flush=True,
        )
        for page in self.pages:
            while not self._stop.is_set():
                stamp = self._facit_stamp()
                models = load_facit(self.facit)
                report = scan_page(
                    self.jsonl,
                    page,
                    models,
                    threshold=self.threshold,
                    stop_after_first_defect=True,
                    progress_store=self.progress_store,
                )
                if not report["defects"]:
                    cached = " (cachad)" if report.get("cached_complete") else ""
                    self.printer(
                        f"batch-prefetch page={page}: EXAKT{cached}; går vidare",
                        flush=True,
                    )
                    break

                first = report["defects"][0]
                self.printer(
                    f"batch-prefetch page={page}: väntar vid col={first['column']} "
                    f"row={first['row']} unknown={first['unknown_pixels']}; "
                    "fortsätter automatiskt när facit ändras",
                    flush=True,
                )
                if not self._wait_for_facit_change(stamp):
                    return
                self.printer(
                    f"batch-prefetch page={page}: facit ändrat; provar vidare",
                    flush=True,
                )

        if not self._stop.is_set():
            self.printer("batch-prefetch: alla senare valda sidor är genomgångna", flush=True)
