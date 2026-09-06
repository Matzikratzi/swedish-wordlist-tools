from __future__ import annotations

"""Time the conservative baseline race without changing the OCR implementation."""

from . import ocr_sequential_raw_page_rows_racesafe as _conservative  # noqa: F401
from . import ocr_raw_page_baseline_timing_debug as timing


if __name__ == "__main__":
    raise SystemExit(timing.main())
