from __future__ import annotations

from .saol_slot_interpreter import SlotGrammar, interpret_single_slot_sequence


_BASIC_VERB_SLOTS = ("preterite", "supine")
_VERB_POSITIONAL_SLOTS = (
    "preterite",
    "supine",
    "perfect_participle_common",
    "perfect_participle_neuter",
    "perfect_participle_plural",
)


def _implicit_basic_verb_slot(index, _last_slot, _operation):
    if 0 <= index < len(_BASIC_VERB_SLOTS):
        return _BASIC_VERB_SLOTS[index]
    return None


def _implicit_verb_slot(index, _last_slot, _operation):
    if 0 <= index < len(_VERB_POSITIONAL_SLOTS):
        return _VERB_POSITIONAL_SLOTS[index]
    return None


BASIC_VERB_GRAMMAR = SlotGrammar(
    label_slots={},
    implicit_slot=_implicit_basic_verb_slot,
)

VERB_GRAMMAR = SlotGrammar(
    label_slots={
        "pres.": "present",
        "imper.": "imperative",
        "n.": "perfect_participle_neuter",
    },
    implicit_slot=_implicit_verb_slot,
)


def _source_tokens(assigned):
    result = []
    for operation in assigned:
        if operation.token not in result:
            result.append(operation.token)
    return tuple(result)


def interpret_basic_verb_sequence(text: str):
    """Interpret the canonical two-atom SAOL verb sequence.

    In unlabelled verb notation the first form atom is preterite and the second
    is supine.  The atoms themselves remain generic SAOL operations: append,
    replacement, unchanged, optional expansion, or a fully written form.

    This deliberately handles only the two-atom core.  Richer labelled and
    participial sequences are handled by :func:`interpret_verb_sequence`.
    """

    assigned = interpret_single_slot_sequence(text, BASIC_VERB_GRAMMAR)
    if assigned is None or len(assigned) < 2:
        return None
    source_tokens = _source_tokens(assigned)
    if len(source_tokens) != 2:
        return None
    if assigned[0].slot != "preterite" or assigned[-1].slot != "supine":
        return None
    return assigned


def interpret_verb_sequence(text: str):
    """Interpret the common SAOL verb slot sequence without paradigm regexes.

    Unlabelled source atoms occupy, in order, preterite, supine and the three
    positive perfect-participle slots (common, neuter, plural).  ``pres.`` and
    ``imper.`` select their named finite slots, while ``n.`` selects the neuter
    perfect participle.  Alternatives remain generic shared-engine alternatives.

    The function intentionally requires at least preterite + supine.  Other
    editorial or grammatical structures are added only when the source
    inventory demonstrates their meaning.
    """

    assigned = interpret_single_slot_sequence(text, VERB_GRAMMAR)
    if assigned is None:
        return None
    occupied = {operation.slot for operation in assigned}
    if "preterite" not in occupied or "supine" not in occupied:
        return None
    return assigned
