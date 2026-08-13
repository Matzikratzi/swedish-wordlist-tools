from __future__ import annotations

from typing import Any

from .compare_sources import _saol_upos
from .generate_adjective_forms import generated_row as generated_adjective_row
from .generate_noun_forms import canonical_noun_row
from .generate_verb_forms import generated_row as generated_verb_row
from .saol_variant_base import prepare_printed_variant_record


def generated_real_shared_row(record: dict[str, Any]) -> dict[str, Any] | None:
    """Generate one real NOUN/ADJ/VERB row using SAOL's printed variant base.

    This is the production-facing shared entry point.  A full word-class row
    with ``ord`` different from ``normaliserat_ord`` is an independent variant
    paradigm: its notation applies to the printed spelling.  The underlying
    class-specific interpreters remain unchanged and receive only the prepared
    structural row.
    """

    target = _saol_upos(record)
    prepared = prepare_printed_variant_record(record)
    if target == "NOUN":
        row, _comparison = canonical_noun_row(prepared)
        return row
    if target == "ADJ":
        return generated_adjective_row(prepared)
    if target == "VERB":
        return generated_verb_row(prepared)
    return None
