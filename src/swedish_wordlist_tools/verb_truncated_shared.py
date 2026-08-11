from __future__ import annotations

from .verb_shared_slot_interpreter import (
    interpret_basic_verb_sequence,
    interpret_present_first_verb_sequence,
    interpret_verb_sequence,
)


def assign_truncated_verb_branch(tokens: tuple[str, ...]):
    """Return the longest safely interpretable visible prefix of a truncated verb branch.

    Source policy decides whether a row is truncated.  Tokenization has two
    deliberately different boundary semantics: an exact 50-character source
    drops its final (possibly cut) token before this function is called, whereas
    a 49-character source keeps its complete final token.  In either case this
    function only interprets evidenced visible atoms and never assumes that the
    paradigm ends at the recovered prefix.
    """

    for end in range(len(tokens), 0, -1):
        prefix = tokens[:end]
        text = " ".join(prefix)

        assigned = interpret_basic_verb_sequence(text)
        if assigned is None:
            assigned = interpret_present_first_verb_sequence(text)
        if assigned is None:
            assigned = interpret_verb_sequence(text)
        if assigned is not None:
            return assigned
    return None
