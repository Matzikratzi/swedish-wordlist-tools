from __future__ import annotations

"""Redirect the v2 aggregate write into the canonical per-model facit store.

The existing editors still pass the historical aggregate path around. To keep
those command lines stable while making ``glyphs/facit-v2`` canonical, install a
narrow ``Path.write_text`` redirect for exactly
``saol14-manual-glyph-facit-v2.json``. The payload is persisted to the split
store first and the aggregate is then regenerated from that store.

No other Path.write_text calls are changed.
"""

import json
from pathlib import Path
from threading import Lock

from .ocr_glyph_facit_store import (
    CANONICAL_AGGREGATE_NAME,
    FACIT_V2,
    persist_facit_payload,
)

_original_write_text = Path.write_text
_install_lock = Lock()
_installed = False


def _canonical_write_text(
    self: Path,
    data: str,
    encoding: str | None = None,
    errors: str | None = None,
    newline: str | None = None,
) -> int:
    if self.name == CANONICAL_AGGREGATE_NAME and isinstance(data, str):
        try:
            payload = json.loads(data)
        except (TypeError, json.JSONDecodeError):
            payload = None
        if isinstance(payload, dict) and payload.get("format") == FACIT_V2:
            persist_facit_payload(self, payload)
            return len(data)
    return _original_write_text(self, data, encoding=encoding, errors=errors, newline=newline)


def install_facit_write_redirect() -> None:
    global _installed
    with _install_lock:
        if _installed:
            return
        Path.write_text = _canonical_write_text
        _installed = True
