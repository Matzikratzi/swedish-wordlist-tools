from __future__ import annotations

from .lexeme_slots import LexemeSlots, SlotForm, build_lexeme_slots

# Legacy slots remain the public compatibility layer while the precise slots
# describe grammatical function explicitly. Only forms already present in the
# interpreted row are copied; this module never invents additional forms.
_PRECISE_ACTIVE_SLOT = {
    "infinitive": "infinitive_active",
    "present": "present_active",
    "preterite": "preterite_active",
    "supine": "supine_active",
}


def add_precise_active_verb_slots(slots: LexemeSlots) -> LexemeSlots:
    """Return ``slots`` enriched with explicit active-voice slot aliases.

    Different verbs legitimately expose different subsets of the paradigm.
    Therefore only legacy slots that actually contain forms are mirrored. The
    original slots are retained so existing validators and reports keep their
    behaviour during the migration to the more precise schema.
    """
    if slots.upos != "VERB":
        return slots

    forms = list(slots.forms)
    existing = {(form.slot, form.written_form) for form in forms}
    changed = False

    for legacy_slot, precise_slot in _PRECISE_ACTIVE_SLOT.items():
        for written_form in slots.forms_for(legacy_slot):
            key = (precise_slot, written_form)
            if key in existing:
                continue
            forms.append(
                SlotForm(
                    precise_slot,
                    written_form,
                    f"active-alias:{legacy_slot}",
                )
            )
            existing.add(key)
            changed = True

    if not changed:
        return slots

    metadata = dict(slots.metadata)
    metadata["verb_slot_schema"] = "legacy-plus-precise-active-v1"
    return build_lexeme_slots(
        lemma=slots.lemma,
        upos=slots.upos,
        notation=slots.notation,
        forms=forms,
        metadata=metadata,
    )
