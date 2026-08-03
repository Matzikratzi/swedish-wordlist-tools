from __future__ import annotations

import re
from typing import Any

from .inflect import normalise_pattern
from .lexeme_slots import LexemeSlots, SlotForm, build_lexeme_slots

_FORM_TOKEN_RE = re.compile(r"[+\-]?[A-Za-zÅÄÖåäöÉéÜü]+(?:-[A-Za-zÅÄÖåäöÉéÜü]+)*")


def _apply_suffix(lemma: str, token: str) -> str:
    if token.startswith("+"):
        suffix = token[1:]
        first, separator, rest = lemma.partition(" ")
        return first + suffix + (separator + rest if separator else "")
    return token


def _tokens(pattern: str) -> tuple[str, ...] | None:
    matches = tuple(match.group(0) for match in _FORM_TOKEN_RE.finditer(pattern))
    remainder = _FORM_TOKEN_RE.sub(" ", pattern)
    if remainder.strip():
        return None
    return matches or None


def interpret_verb_slots(record: dict[str, Any]) -> LexemeSlots | None:
    """Interpret ordinary SAOL verb notation into generic grammatical slots.

    The infinitive is the lemma. Two supplied forms are interpreted as
    preterite and supine, matching compact SAOL rows such as ``+de +t``.
    Three supplied forms are interpreted as present, preterite and supine,
    matching explicit irregular rows such as ``går gick gått``.
    """
    if str(record.get("upos", "")).upper() != "VERB":
        return None
    lemma = str(record.get("normaliserat_ord", "")).strip()
    pattern = normalise_pattern(record.get("text"))
    if not lemma or pattern is None:
        return None

    tokens = _tokens(pattern)
    if tokens is None or len(tokens) not in {2, 3}:
        return None

    if len(tokens) == 2:
        assignments = (("preterite", tokens[0]), ("supine", tokens[1]))
    else:
        assignments = (
            ("present", tokens[0]),
            ("preterite", tokens[1]),
            ("supine", tokens[2]),
        )

    forms = [SlotForm("infinitive", lemma, "lemma")]
    forms.extend(
        SlotForm(slot, _apply_suffix(lemma, token), token)
        for slot, token in assignments
    )
    return build_lexeme_slots(
        lemma=lemma,
        upos="VERB",
        notation=pattern,
        forms=forms,
        metadata={
            "record_id": str(record.get("id") or record.get("subnr") or ""),
            "homonym_number": str(record.get("homonr") or ""),
            "stycke": str(record.get("stycke") or ""),
            "ordkl": str(record.get("ordkl") or ""),
        },
    )
