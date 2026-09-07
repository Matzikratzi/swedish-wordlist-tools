"""Tools for building Swedish word lists."""

__version__ = "0.1.0"

# Reject false physical rows whose first ink starts beyond the page's learned
# continuation indent. Detached upper glyph parts are absorbed into the nearest
# real neighbour row instead of becoming standalone rows.
from .ocr_row_start_limit import install_row_start_limit

install_row_start_limit()

# Install the shared SAOL OCR left-edge safety margin before row-OCR modules
# import the persistent-left-rule helper by value.
from .ocr_left_crop_safety import install_left_crop_safety_margin

install_left_crop_safety_margin()

# Install the deterministic one-time B -> B+1 baseline fallback before editor,
# batch scanner and benchmark layers import the shared analyser by value.
from .ocr_shared_single_downshift import install_shared_single_downshift

install_shared_single_downshift()

# A completely unrecognized row has no OCR baseline. The glyph editor must still
# be able to bootstrap it by saving a manually selected glyph against the row's
# geometric support line (or an explicitly edited baseline).
from .ocr_manual_baseline_editor import install_manual_baseline_editor

install_manual_baseline_editor()
