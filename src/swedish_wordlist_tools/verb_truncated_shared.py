from __future__ import annotations

from .saol_notation import parse_form_operations
from .verb_shared_slot_interpreter import (
    interpret_basic_verb_sequence,
    interpret_present_first_verb_sequence,
    interpret_verb_sequence,
)


def _contains_visible_form_atom(tokens: tuple[str, ...]) -> bool:
    """Return true when the prefix contains at least one evidenced form atom.

    Complete verb notation may legitimately consist only of a slot label, e.g.
    ``pres.`` meaning that the lemma itself is the present form.  That inference
    is unsafe for a truncated source: the form belonging to a trailing label may
    have existed beyond the export boundary.  Partial recovery therefore requires
    an actual visible form token (relative operation or fully written form).
    """

    return any(parse_form_operations(token) is not None for token in tokens)


def assign_truncated_verb_branch(tokens: tuple[str, ...]):
    """Return the longest safely interpretable visible prefix of a truncated verb branch.

    Source policy decides whether a row is truncated. Tokenization has two
    deliberately different boundary semantics: an exact 50-character source
    drops its final (possibly cut) token before this function is called, whereas
    a 49-character source keeps its complete final token. In either case this
    function only interprets evidenced visible atoms and never assumes that the
    paradigm ends at the recovered prefix.

    A label-only prefix is never enough here. Although complete SAOL notation
    such as ``pres.`` can mean that the lemma itself occupies that slot, on a
    truncated row the form following the label may simply have been cut away.
    """

    for end in range(len(tokens), 0, -1):
        prefix = tokens[:end]
        if not _contains_visible_form_atom(prefix):
            continue
        text = " ".join(prefix)

        assigned = interpret_basic_verb_sequence(text)
        if assigned is None:
            assigned = interpret_present_first_verb_sequence(text)
        if assigned is None:
            assigned = interpret_verb_sequence(text)
        if assigned is not None:
            return assigned
    return None
