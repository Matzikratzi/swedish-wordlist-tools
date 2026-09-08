from __future__ import annotations

"""Canonical loading for the SAOL14 v2 glyph facit.

The per-model ``facit-v2`` store is the durable source of truth. The historical
aggregate JSON remains a compatibility artefact for old command lines and
editors; canonical project loads reconstruct their payload from the split store.
"""

from pathlib import Path
import json
import tempfile

from .ocr_glyph_facit_store import canonical_store_for_facit, load_split_facit
from .ocr_glyph_review_delete import load_facit_with_typography


def load_canonical_facit_with_typography(facit_path: Path):
    """Load split-store truth for the canonical v2 aggregate path.

    Explicit non-canonical JSON paths retain legacy semantics so frozen fixtures
    remain usable. The temporary aggregate is only an adapter into the existing
    model parser; its bytes come solely from the split store.
    """
    facit_path = Path(facit_path)
    store = canonical_store_for_facit(facit_path)
    if store is None:
        return load_facit_with_typography(facit_path)
    if not store.is_dir():
        raise FileNotFoundError(
            f"canonical facit store is missing: {store}; "
            f"{facit_path.name} is only a compatibility aggregate"
        )
    payload = load_split_facit(store)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", encoding="utf-8") as tmp:
        json.dump(payload, tmp, ensure_ascii=False)
        tmp.flush()
        return load_facit_with_typography(Path(tmp.name))
