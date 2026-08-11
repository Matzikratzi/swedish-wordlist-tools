from __future__ import annotations

from .saol_slot_interpreter import SlotGrammar, interpret_single_slot_sequence


_BASIC_VERB_SLOTS = ("preterite", "supine")


def _implicit_basic_verb_slot(index, _last_slot, _operation):
    if 0 <= index < len(_BASIC_VERB_SLOTS):
        return _BASIC_VERB_SLOTS[index]
    return None


BASIC_VERB_GRAMMAR = SlotGrammar(
    label_slots={},
    implicit_slot=_implicit_basic_verb_slot,
)


def interpret_basic_verb_sequence(text: str):
    """Interpret the canonical two-atom SAOL verb sequence.

    In unlabelled verb notation the first form atom is preterite and the second
    is supine.  The atoms themselves remain generic SAOL operations: suffix,
    replacement, unchanged, optional expansion, or a fully written form.

    This deliberately handles only the two-atom core.  Longer paradigms and
    labelled forms (present, imperative, participles, etc.) are layered on top
    once their source structure has been inventoried.
    """

    assigned = interpret_single_slot_sequence(text, BASIC_VERB_GRAMMAR)
    if assigned is None or len(assigned) < 2:
        return None
    if {operation.slot for operation in assigned} - set(_BASIC_VERB_SLOTS):
        return None
    # Exactly two source tokens/slots are required. Optional notation may
    # expand one token to multiple primitive operations in the same slot.
    source_tokens = []
    for operation in assigned:
        if operation.token not in source_tokens:
            source_tokens.append(operation.token)
    if len(source_tokens) != 2:
        return None
    if assigned[0].slot != "preterite" or assigned[-1].slot != "supine":
        return None
    return assigned
