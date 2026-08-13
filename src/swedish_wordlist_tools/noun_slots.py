from __future__ import annotations

from typing import Any

from .lexeme_slots import LexemeSlots, SlotForm, build_lexeme_slots
from .saol_row_interpreter import InterpretedRow, interpret_noun_row


def noun_row_to_slots(record: dict[str, Any], row: InterpretedRow) -> LexemeSlots:
    """Convert the noun interpreter result to the generic slot representation."""
    metadata = {
        "record_id": str(record.get("id") or record.get("subnr") or ""),
        "homonym_number": str(record.get("homonr") or ""),
        "stycke": str(record.get("stycke") or ""),
        "ordkl": str(record.get("ordkl") or ""),
    }
    return build_lexeme_slots(
        lemma=row.lemma,
        upos="NOUN",
        notation=row.pattern,
        forms=(
            SlotForm(form.slot, form.written_form, form.source)
            for form in row.key_forms
        ),
        metadata=metadata,
    )


def interpret_noun_slots(record: dict[str, Any]) -> LexemeSlots | None:
    """Interpret one SAOL noun row into word-class-independent slots."""
    row = interpret_noun_row(record)
    if row is None:
        return None
    return noun_row_to_slots(record, row)
