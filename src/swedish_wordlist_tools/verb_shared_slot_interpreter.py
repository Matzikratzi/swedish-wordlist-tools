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


def is_structurally_uninflected_verb(text: str) -> bool:
    """Return true for SAOL's explicit ``ingen böjning`` notation."""

    normalized = " ".join(text.casefold().replace(";", " ").replace(",", " ").split())
    return normalized == "ingen: böjning:"


def interpret_verb_sequence(text: str):
    """Interpret common and defective SAOL verb notation atomically.

    Unlabelled source atoms occupy, in order, preterite, supine and the three
    positive perfect-participle slots. Named labels may instead select present,
    preterite, supine, imperative or participle slots explicitly. Editorial
    qualifiers are transparent; ``el.``/``H`` reuse the preceding slot.

    Unlike the first bootstrap version, this function does not require both
    preterite and supine. SAOL contains genuinely defective paradigms, e.g.
    ``djärvdes, pres. djärvs el. djärves`` and ``pres. -fås, sup. -fåtts``.
    A structurally explicit named/marked sequence is valid even when a normal
    paradigm slot is absent.
    """

    if is_structurally_uninflected_verb(text):
        return ()
    assigned = interpret_single_slot_sequence(text, VERB_GRAMMAR)
    if assigned is None:
        return None
    return assigned
