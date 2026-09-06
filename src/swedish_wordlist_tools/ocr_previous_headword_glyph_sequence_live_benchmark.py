from __future__ import annotations

"""Run previous-headword glyph-sequence priority inside the live-row wrapper.

The live-row benchmark installs its own ``_load_owned_row_state`` wrapper after
outer benchmark wrappers have started.  Point its underlying loader at the
sequence tracker so headword memory is actually observed while retaining the
existing live timing/distribution diagnostics.
"""

from . import ocr_live_row_trace_benchmark as live
from . import ocr_previous_headword_glyph_sequence_benchmark as sequence


def main() -> int:
    original_live_loader = live._ORIGINAL
    live._ORIGINAL = sequence._tracked_load
    try:
        return sequence.main()
    finally:
        live._ORIGINAL = original_live_loader


if __name__ == "__main__":
    raise SystemExit(main())
