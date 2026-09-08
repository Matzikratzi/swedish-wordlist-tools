from __future__ import annotations
"""Canonical loading for the SAOL14 v2 glyph facit.

``facit-v2`` is durable truth. The aggregate JSON is a compatibility name for
that store; explicit differently named JSON fixtures keep legacy semantics.
"""
import json,tempfile
from pathlib import Path
from .ocr_glyph_facit_store import canonical_store_for_facit,load_split_facit
from .ocr_glyph_review_delete import load_facit_with_typography
def load_canonical_facit_with_typography(facit_path:Path):
 facit_path=Path(facit_path);store=canonical_store_for_facit(facit_path)
 if store is None:return load_facit_with_typography(facit_path)
 if not store.is_dir():raise FileNotFoundError(f"canonical facit store is missing: {store}; {facit_path.name} is only a compatibility aggregate")
 payload=load_split_facit(store)
 with tempfile.TemporaryDirectory() as td:
  adapter=Path(td)/"facit.json";adapter.write_text(json.dumps(payload,ensure_ascii=False)+"\n",encoding="utf-8");return load_facit_with_typography(adapter)
