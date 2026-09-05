from __future__ import annotations

"""Timing wrapper around ``ocr_raw_page_baseline_debug``.

The OCR debug CLI now writes JSONL only; image rendering is a separate process.
With ``--all`` this command dispatches to the whole-page sequential runner.
"""

from functools import wraps
import sys
from time import perf_counter

from . import ocr_raw_page_baseline_debug as debug
from . import ocr_sequential_raw_page_rows_exactmatch as _exactmatch  # noqa: F401


_TOTALS = {"setup": 0.0, "ocr": 0.0}


def _wrap(namespace, name: str, label: str, *, bucket: str | None = None) -> None:
    original = getattr(namespace, name)

    @wraps(original)
    def timed(*args, **kwargs):
        started = perf_counter()
        try:
            return original(*args, **kwargs)
        finally:
            elapsed = perf_counter() - started
            if bucket is not None:
                _TOTALS[bucket] += elapsed
            print(f"raw-page-timing: {label}={elapsed:.6f}s")

    setattr(namespace, name, timed)


def _install_timers() -> None:
    _wrap(debug, "load_facit_with_typography", "load-facit", bucket="setup")
    _wrap(debug.page_editor, "build_page_context_pixel_array", "build-page-context", bucket="setup")
    _wrap(debug.cached, "bind_page_candidates", "bind-page-candidates", bucket="setup")
    _wrap(debug, "_load_thresholded_page", "load-thresholded-page", bucket="setup")
    _wrap(debug, "_install_page1_raw_layout", "install-page1-layout", bucket="setup")

    original_ensure = debug.sequential.ensure_row_cached

    @wraps(original_ensure)
    def timed_ensure(context, column, target_row, models):
        started = perf_counter()
        try:
            return original_ensure(context, column, target_row, models)
        finally:
            elapsed = perf_counter() - started
            _TOTALS["ocr"] += elapsed
            print(f"raw-page-timing: ensure-row row={target_row:03d}={elapsed:.6f}s")

    debug.sequential.ensure_row_cached = timed_ensure


def main() -> int:
    if "--all" in sys.argv[1:]:
        from . import ocr_raw_page_baseline_all

        # The whole-page runner has its own aggregate timing and intentionally
        # accepts neither --column nor --row.
        sys.argv = [arg for arg in sys.argv if arg != "--all"]
        return ocr_raw_page_baseline_all.main()

    for key in _TOTALS:
        _TOTALS[key] = 0.0

    _install_timers()
    started = perf_counter()
    try:
        return debug.main()
    finally:
        elapsed = perf_counter() - started
        accounted = _TOTALS["setup"] + _TOTALS["ocr"]
        other = max(0.0, elapsed - accounted)
        print(f"raw-page-timing: debug-main-total={elapsed:.6f}s")
        print(
            "raw-page-timing-summary: "
            f"ocr={_TOTALS['ocr']:.6f}s setup={_TOTALS['setup']:.6f}s "
            f"other={other:.6f}s total={elapsed:.6f}s render=separate-process"
        )


if __name__ == "__main__":
    raise SystemExit(main())
