from __future__ import annotations

from typing import Any

from .generate_adjective_forms import generated_row as generated_adjective_row
from .inflect import generate_entry
from .noun_paradigm import complete_noun_entry
from .verb_game_fallback import interpret_playable_verb_slots
from .verb_slot_schema import add_explicit_verb_row_slots


def canonical_record_forms(record: dict[str, Any]) -> set[str]:
    """Return forms from the canonical generator for the record's word class.

    This is intentionally record-local. Corpus-level verb compound-head repairs are
    audited separately and are not needed to replace the legacy direct generator for
    ordinary directly matched verb rows.
    """

    upos = str(record.get("upos") or "").upper()

    if upos == "NOUN":
        initial = generate_entry(record)
        completed = complete_noun_entry(record, initial)
        entry = completed or initial
        return set(entry.forms if entry is not None else ())

    if upos == "ADJ":
        row = generated_adjective_row(record)
        if row is None:
            return set()
        return {
            str(form["written_form"])
            for form in row["forms"]
            if str(form.get("written_form") or "")
        }

    if upos == "VERB":
        slots = interpret_playable_verb_slots(record)
        if slots is None:
            return set()
        slots = add_explicit_verb_row_slots(record, slots)
        return set(slots.written_forms())

    entry = generate_entry(record)
    return set(entry.forms if entry is not None else ())
