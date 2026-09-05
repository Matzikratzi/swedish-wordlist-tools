from __future__ import annotations

"""Timing wrapper around ``ocr_raw_page_baseline_debug``.

This deliberately does not change OCR behaviour.  It wraps the expensive
high-level operations used by the existing debug CLI and prints wall-clock
breakdowns so we can distinguish OCR work from page preparation and PNG
rendering.
"""

from functools import wraps
from time import perf_counter

from . import ocr_raw_page_baseline_debug as debug


def _wrap(namespace, name: str, label: str) -> None:
    original = getattr(namespace, name)

    @wraps(original)
    def timed(*args, **kwargs):
        started = perf_counter()
        try:
            return original(*args, **kwargs)
        finally:
            elapsed = perf_counter() - started
            print(f"raw-page-timing: {label}={elapsed:.6f}s")

    setattr(namespace, name, timed)


def _install_timers() -> None:
    # One-time setup phases.
    _wrap(debug, "load_facit_with_typography", "load-facit")
    _wrap(
        debug.page_editor,
        "build_page_context_pixel_array",
        "build-page-context",
    )
    _wrap(debug.cached, "bind_page_candidates", "bind-page-candidates")
    _wrap(debug, "_load_thresholded_page", "load-thresholded-page")
    _wrap(debug, "_install_page1_raw_layout", "install-page1-layout")

    # Sequential OCR.  main() calls ensure_row_cached once for every target row;
    # after row 0 each call only discovers the newly requested row because the
    # previous rows are cached.
    original_ensure = debug.sequential.ensure_row_cached

    @wraps(original_ensure)
    def timed_ensure(context, column, target_row, models):
        started = perf_counter()
        try:
            return original_ensure(context, column, target_row, models)
        finally:
            elapsed = perf_counter() - started
            print(
                "raw-page-timing: "
                f"ensure-row row={target_row:03d}={elapsed:.6f}s"
            )

    debug.sequential.ensure_row_cached = timed_ensure

    # Rendering is intentionally measured separately.  The existing CLI writes
    # both a per-row snapshot and the rolling output image after every row, so
    # this may account for substantial wall time without being OCR cost.
    original_draw = debug._draw_snapshot

    @wraps(original_draw)
    def timed_draw(*args, **kwargs):
        started = perf_counter()
        output = kwargs.get("output")
        if output is None and len(args) >= 5:
            output = args[4]
        try:
            return original_draw(*args, **kwargs)
        finally:
            elapsed = perf_counter() - started
            print(
                "raw-page-timing: "
                f"draw-snapshot={elapsed:.6f}s output={output}"
            )

    debug._draw_snapshot = timed_draw


def main() -> int:
    _install_timers()
    started = perf_counter()
    try:
        return debug.main()
    finally:
        elapsed = perf_counter() - started
        print(f"raw-page-timing: debug-main-total={elapsed:.6f}s")


if __name__ == "__main__":
    raise SystemExit(main())
