from __future__ import annotations

"""Run the frozen-reference comparator with the conservative baseline race.

Importing ``ocr_sequential_raw_page_rows_racesafe`` installs the conservative
full baseline race from commit 026bc00 before the comparator imports the debug
scanner.  Keep this wrapper as the correctness benchmark for the rebuild so
later optimizations can be compared against one explicit baseline.
"""

from . import ocr_sequential_raw_page_rows_racesafe as _conservative  # noqa: F401
from . import ocr_compare_raw_page_reference as comparator


if __name__ == "__main__":
    raise SystemExit(comparator.main())
