from __future__ import annotations

from .saol_notation import FormOperationKind
from .saol_slot_interpreter import SlotGrammar, interpret_single_slot_sequence


_BASIC_VERB_SLOTS = ("preterite", "supine")
_VERB_POSITIONAL_SLOTS = (
    "preterite",
    "supine",
    "perfect_participle_common",
    "perfect_participle_neuter",
    "perfect_participle_plural",
)
_PRESENT_FIRST_VERB_SLOTS = (
    "present",
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


def _implicit_present_first_verb_slot(index, _last_slot, _operation):
    if 0 <= index < len(_PRESENT_FIRST_VERB_SLOTS):
        return _PRESENT_FIRST_VERB_SLOTS[index]
    return None


BASIC_VERB_GRAMMAR = SlotGrammar(
    label_slots={},
    implicit_slot=_implicit_basic_verb_slot,
)

VERB_GRAMMAR = SlotGrammar(
    label_slots={
        "pres.": "present",
        "pret.": "preterite",
        "sup.": "supine",
        "imper.": "imperative",
        "perf.": "perfect_participle_common",
        "part.": "perfect_participle_common",
        "n.": "perfect_participle_neuter",
    },
    implicit_slot=_implicit_verb_slot,
    # ``el.`` and ``H`` introduce another realization of the preceding slot.
    # H is Språkbanken's encoding of SAOL's ``hellre än`` relation; the shared
    # SlotOperation preserves that preference as metadata without changing the
    # grammatical slot.
    alternative_markers=frozenset({"el.", "h"}),
    transparent_markers=frozenset({
        "i:",
        "som:",
        "används:",
        "anv.",
        "prov.",
        "vard.",
        "åld.",
        "ibl.",
        "obrukl.",
        "finl.",
    }),
    bare_label_as_unchanged=True,
    allow_trailing_incomplete_alternative=True,
)

PRESENT_FIRST_VERB_GRAMMAR = SlotGrammar(
    label_slots={},
    implicit_slot=_implicit_present_first_verb_slot,
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
    is supine. The atoms themselves remain generic SAOL operations: append,
    replacement, unchanged, optional expansion, or a fully written form.
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


def interpret_present_first_verb_sequence(text: str):
    """Interpret a complete six-form sequence whose present form is written first.

    SAOL occasionally writes a full explicit paradigm as present, preterite,
    supine and three perfect-participle forms without labels, e.g.
    ``föräter, föråt, förätit, föräten förätet förätna``.  Requiring exactly six
    explicit source atoms keeps this positional grammar distinct from the normal
    preterite-first notation.
    """

    assigned = interpret_single_slot_sequence(text, PRESENT_FIRST_VERB_GRAMMAR)
    if assigned is None:
        return None
    if len(_source_tokens(assigned)) != 6:
        return None
    if tuple(item.slot for item in assigned) != _PRESENT_FIRST_VERB_SLOTS:
        return None
    if any(item.operation.kind is not FormOperationKind.EXPLICIT for item in assigned):
        return None
    return assigned


def is_structurally_uninflected_verb(text: str) -> bool:
    """Return true for SAOL's explicit ``ingen böjning`` notation."""

    normalized = " ".join(text.casefold().replace(";", " ").replace(",", " ").split())
    return normalized == "ingen: böjning:"


def interpret_verb_sequence(text: str):
    """Interpret common and defective SAOL verb notation atomically.

    Unlabelled source atoms normally occupy, in order, preterite, supine and the
    three positive perfect-participle slots. A complete six-form explicit
    sequence may instead start with present and is recognized independently.
    Named labels select present, preterite, supine, imperative or participle
    slots explicitly. Editorial qualifiers are transparent; ``el.``/``H`` reuse
    the preceding slot. A trailing incomplete alternative may be ignored without
    inventing its missing form.
    """

    if is_structurally_uninflected_verb(text):
        return ()
    present_first = interpret_present_first_verb_sequence(text)
    if present_first is not None:
        return present_first
    assigned = interpret_single_slot_sequence(text, VERB_GRAMMAR)
    if assigned is None:
        return None
    return assigned
