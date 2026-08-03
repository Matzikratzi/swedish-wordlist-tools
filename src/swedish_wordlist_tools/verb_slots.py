from __future__ import annotations

import re
from typing import Any

from .inflect import normalise_pattern
from .lexeme_slots import LexemeSlots, SlotForm, build_lexeme_slots
from .saol_row_interpreter import apply_form_token

_FORM_TOKEN_RE = re.compile(r"[+\-]?[A-Za-zÅÄÖåäöÉéÜü]+(?:-[A-Za-zÅÄÖåäöÉéÜü]+)*")
_MARKER_RE = re.compile(r"\b(?:el\.|vard\.|åld\.|n\.)\b", re.IGNORECASE)
_PRESENT_RE = re.compile(r"(?:^|[,;])\s*pres\.\s*", re.IGNORECASE)


def _apply_token(record: dict[str, Any], lemma: str, token: str) -> str | None:
    return apply_form_token(record, lemma, token)


def _tokens(pattern: str) -> tuple[str, ...] | None:
    matches = tuple(match.group(0) for match in _FORM_TOKEN_RE.finditer(pattern))
    remainder = _FORM_TOKEN_RE.sub(" ", pattern)
    if remainder.strip():
        return None
    return matches or None


def _alternative_tokens(text: str) -> tuple[str, ...]:
    """Extract form alternatives while discarding lexicographic markers."""
    cleaned = _MARKER_RE.sub(" ", text)
    tokens = tuple(match.group(0) for match in _FORM_TOKEN_RE.finditer(cleaned))
    return tuple(token for token in tokens if token.casefold() not in {"el", "vard", "åld", "n"})


def _labelled_assignments(pattern: str) -> tuple[tuple[str, str], ...] | None:
    """Interpret comma groups followed by ``pres.``.

    In SAOL's expanded verb notation the first comma group is preterite, the
    second is supine, following groups describe participles, and the group
    introduced by ``pres.`` contains one or more present-tense alternatives.
    """
    match = _PRESENT_RE.search(pattern)
    if match is None:
        return None

    before = pattern[: match.start()].strip(" ,;")
    after = pattern[match.end() :].strip()
    groups = [part.strip() for part in before.split(",") if part.strip()]
    if len(groups) < 2:
        return None

    assignments: list[tuple[str, str]] = []
    for slot, group in (("preterite", groups[0]), ("supine", groups[1])):
        alternatives = _alternative_tokens(group)
        if not alternatives:
            return None
        assignments.extend((slot, token) for token in alternatives)

    present_group = re.split(r"[,;]", after, maxsplit=1)[0]
    present = _alternative_tokens(present_group)
    if not present:
        return None
    assignments.extend(("present", token) for token in present)
    return tuple(assignments)


def interpret_verb_slots(record: dict[str, Any]) -> LexemeSlots | None:
    """Interpret SAOL verb notation into generic grammatical slots."""
    if str(record.get("upos", "")).upper() != "VERB":
        return None
    lemma = str(record.get("normaliserat_ord", "")).strip()
    pattern = normalise_pattern(record.get("text"))
    if not lemma or pattern is None:
        return None

    assignments = _labelled_assignments(pattern)
    if assignments is None:
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
    for slot, token in assignments:
        written_form = _apply_token(record, lemma, token)
        if written_form is None:
            return None
        forms.append(SlotForm(slot, written_form, token))

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
