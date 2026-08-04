from __future__ import annotations

import re
from typing import Any

from .inflect import normalise_pattern
from .lexeme_slots import LexemeSlots, SlotForm, build_lexeme_slots
from .verb_slots import interpret_verb_slots

_FORM_TOKEN_RE = re.compile(r"[A-Za-zÅÄÖåäöÉéÜü]+(?:-[A-Za-zÅÄÖåäöÉéÜü]+)*")
_PRESENT_ONLY_RE = re.compile(r"^pres\.$", re.IGNORECASE)
_PRESENT_OPTION_RE = re.compile(
    r"^pres\.\s+ibl\.\s+(?P<form>[A-Za-zÅÄÖåäöÉéÜü-]+)$",
    re.IGNORECASE,
)
_SINGLE_FORM_RE = re.compile(r"^[A-Za-zÅÄÖåäöÉéÜü-]+$")
_SUPINE_RE = re.compile(
    r"\bsup\.\s+(?P<form>[A-Za-zÅÄÖåäöÉéÜü-]+)",
    re.IGNORECASE,
)


def _metadata(record: dict[str, Any], *, fallback_kind: str) -> dict[str, str]:
    return {
        "record_id": str(record.get("id") or record.get("subnr") or ""),
        "homonym_number": str(record.get("homonr") or ""),
        "ordkl": str(record.get("ordkl") or ""),
        "fallback_kind": fallback_kind,
    }


def _attested_forms(record: dict[str, Any], lemma: str, pattern: str | None) -> tuple[SlotForm, ...] | None:
    """Return conservative SAOL-attested forms when no paradigm was parsed.

    This is intentionally a game/export fallback, not a grammatical parser.
    The headword is always attested by the SAOL entry. Additional forms are
    included only when they are explicitly written in the compact notation.
    """
    forms = [SlotForm("attested", lemma, "headword")]

    if pattern is None:
        return tuple(forms)

    if _PRESENT_ONLY_RE.fullmatch(pattern):
        return tuple(forms)

    present_option = _PRESENT_OPTION_RE.fullmatch(pattern)
    if present_option is not None:
        forms.append(SlotForm("attested", present_option.group("form"), "explicit_form"))
        return tuple(forms)

    if _SINGLE_FORM_RE.fullmatch(pattern):
        forms.append(SlotForm("attested", pattern, "explicit_form"))
        return tuple(forms)

    supine = _SUPINE_RE.search(pattern)
    if supine is not None and "pres." in pattern.casefold() and "pret." in pattern.casefold():
        forms.append(SlotForm("attested", supine.group("form"), "explicit_supine"))
        return tuple(forms)

    return None


def interpret_playable_verb_slots(record: dict[str, Any]) -> LexemeSlots | None:
    """Interpret a verb for game export, preferring the strict row parser."""
    parsed = interpret_verb_slots(record)
    if parsed is not None:
        return parsed

    if str(record.get("upos", "")).upper() != "VERB":
        return None
    lemma = str(record.get("normaliserat_ord") or "").strip()
    if not lemma:
        return None

    pattern = normalise_pattern(record.get("text"))
    forms = _attested_forms(record, lemma, pattern)
    if forms is None:
        return None

    fallback_kind = "lemma_only" if len(forms) == 1 else "explicit_attested_forms"
    return build_lexeme_slots(
        lemma=lemma,
        upos="VERB",
        notation=pattern or "(none)",
        forms=forms,
        metadata=_metadata(record, fallback_kind=fallback_kind),
    )
