from __future__ import annotations

from .saol_slot_interpreter import SlotGrammar, interpret_single_slot_sequence


_BASIC_VERB_SLOTS = ("preterite", "supine")
# Verified from complete, purely positional SAOL14 rows and checked against
# SALDO MSD. The five-position form is:
#   preterite, supine, perfect participle common/neuter/plural.
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
)


def _source_tokens(assigned):
    result = []
    for operation in assigned:
        if operation.token not in result:
            result.append(operation.token)
    return tuple(result)


def interpret_basic_verb_sequence(text: str):
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
    normalized = " ".join(text.casefold().replace(";", " ").replace(",", " ").split())
    return normalized == "ingen: böjning:"


def interpret_verb_sequence(text: str):
    """Interpret SAOL verb notation with only evidenced positional semantics.

    Complete unlabelled rows support one-position preterite, two-position
    preterite+supine and the five-position sequence ending in three perfect
    participle forms. Explicit labels may add or select other slots.

    Incomplete endings are deliberately rejected here. If the source is known
    to be truncated, source policy and the verb partial-prefix path decide how
    much complete notation may safely be recovered.
    """

    if is_structurally_uninflected_verb(text):
        return ()
    return interpret_single_slot_sequence(text, VERB_GRAMMAR)
