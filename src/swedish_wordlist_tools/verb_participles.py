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
_SOURCE_TEXT_LIMIT = 50


def _third_group_before_present(pattern: str) -> str | None:
    """Return the third comma group only when it ends before any hard cap.

    The source export truncates ``text`` at 50 characters. On a capped row the
    final group is therefore untrusted regardless of how plausible or long its
    last token looks. A third group followed by a comma and ``pres.`` is safe:
    the delimiter proves that the complete group ended before the cap.
    """
    present = _PRESENT_RE.search(pattern)
    if present is None:
        return None

    before_present = pattern[: present.start()].rstrip()
    # The participle group is trusted only when the source contains the comma
    # that terminates it before the present-tense label. This remains true on a
    # 50-character row; a group touching the hard boundary has no such later
    # delimiter and never reaches this parser path.
    if not before_present.rstrip(" ;:").endswith(","):
        return None

    before_present = before_present.rstrip(" ,;:")
    groups = [group.strip(" ;:") for group in before_present.split(",")]
    groups = [group for group in groups if group]
    if len(groups) < 3:
        return None
    return groups[2]


def explicit_perfect_participle_tokens(
    record: Mapping[str, Any],
) -> tuple[str, str, str] | None:
    """Return an explicit three-form perfect-participle group from one row.

    SAOL rows such as ``skrev, skrivit, skriven skrivet skrivna, pres. skriver``
    place the common, neuter and plural participles in the third comma group.
    We accept only exactly three plain form tokens from a group that is visibly
    terminated before any 50-character source truncation. Shorter comments such
    as ``lagd n. lagt`` and explanatory groups are left untouched.
    """
    pattern = normalise_pattern(record.get("text"))
    if pattern is None:
        return None

    group = _third_group_before_present(pattern)
    if group is None:
        return None

    tokens = tuple(match.group(0) for match in _FORM_TOKEN_RE.finditer(group))
    remainder = _FORM_TOKEN_RE.sub(" ", group).strip()
    if remainder or len(tokens) != 3:
        return None
    return tokens  # type: ignore[return-value]


def _apply_participle_token(
    record: Mapping[str, Any], lemma: str, token: str
) -> str | None:
    """Apply a participle token to the lexical verb, not its complements.

    Inflectional verb slots retain reflexive pronouns and particles, e.g.
    ``företog sig``. Perfect participles are standalone word forms for the game
    word list, so ``företa sig`` yields ``företagen`` rather than
    ``företagen sig``. The same rule turns ``dra ihop sig`` + ``dragen`` into
    ``dragen``.
    """
    lexical_verb = lemma.partition(" ")[0]
    return _apply_token(dict(record), lexical_verb, token)


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

    forms = list(slots.forms)
    existing = {(form.slot, form.written_form) for form in forms}
    changed = False
    for slot, token in zip(_PARTICIPLE_SLOTS, tokens):
        written = _apply_participle_token(record, slots.lemma, token)
        if written is None or (slot, written) in existing:
            continue
        forms.append(SlotForm(slot, written, token))
        existing.add((slot, written))
        changed = True

    if not changed:
        return slots
    metadata = dict(slots.metadata)
    metadata["explicit_perfect_participle"] = "row-third-group-v2"
    return build_lexeme_slots(
        lemma=slots.lemma,
        upos=slots.upos,
        notation=slots.notation,
        forms=forms,
        metadata=metadata,
    )
