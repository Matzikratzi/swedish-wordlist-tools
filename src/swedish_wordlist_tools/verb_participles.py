from __future__ import annotations

import re
from typing import Any, Mapping

from .inflect import normalise_pattern
from .lexeme_slots import LexemeSlots, SlotForm, build_lexeme_slots
from .verb_slots import _apply_token

_PRESENT_RE = re.compile(r"\bpres\.\s*", re.IGNORECASE)
_FORM_TOKEN_RE = re.compile(
    r"[+\-]?[A-Za-zÅÄÖåäöÉéÜü]+(?:-[A-Za-zÅÄÖåäöÉéÜü]+)*"
)
_PARTICIPLE_SLOTS = (
    "perfect_participle_common",
    "perfect_participle_neuter",
    "perfect_participle_plural",
)


def explicit_perfect_participle_tokens(
    record: Mapping[str, Any],
) -> tuple[str, str, str] | None:
    """Return an explicit three-form perfect-participle group from one row.

    SAOL rows such as ``skrev, skrivit, skriven skrivet skrivna, pres. skriver``
    place the common, neuter and plural participles in the third comma group.
    We accept only exactly three plain form tokens. Shorter comments such as
    ``lagd n. lagt`` and longer explanatory groups are left untouched.
    """
    pattern = normalise_pattern(record.get("text"))
    if pattern is None:
        return None
    present = _PRESENT_RE.search(pattern)
    if present is None:
        return None

    before_present = pattern[: present.start()].strip(" ,;:")
    groups = [group.strip(" ;:") for group in before_present.split(",")]
    groups = [group for group in groups if group]
    if len(groups) < 3:
        return None

    tokens = tuple(match.group(0) for match in _FORM_TOKEN_RE.finditer(groups[2]))
    remainder = _FORM_TOKEN_RE.sub(" ", groups[2]).strip()
    if remainder or len(tokens) != 3:
        return None
    return tokens  # type: ignore[return-value]


def add_explicit_perfect_participles(
    record: Mapping[str, Any],
    slots: LexemeSlots,
) -> LexemeSlots:
    """Add only perfect-participle forms explicitly present on ``record``."""
    if slots.upos != "VERB":
        return slots
    tokens = explicit_perfect_participle_tokens(record)
    if tokens is None:
        return slots

    mutable_record = dict(record)
    forms = list(slots.forms)
    existing = {(form.slot, form.written_form) for form in forms}
    changed = False
    for slot, token in zip(_PARTICIPLE_SLOTS, tokens):
        written = _apply_token(mutable_record, slots.lemma, token)
        if written is None or (slot, written) in existing:
            continue
        forms.append(SlotForm(slot, written, token))
        existing.add((slot, written))
        changed = True

    if not changed:
        return slots
    metadata = dict(slots.metadata)
    metadata["explicit_perfect_participle"] = "row-third-group-v1"
    return build_lexeme_slots(
        lemma=slots.lemma,
        upos=slots.upos,
        notation=slots.notation,
        forms=forms,
        metadata=metadata,
    )
