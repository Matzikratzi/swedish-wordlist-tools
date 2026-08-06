from __future__ import annotations

import re
from typing import Any

from .inflect import normalise_pattern
from .lexeme_slots import LexemeSlots, SlotForm, build_lexeme_slots
from .verb_residual_policy import interpret_residual_verb_slots
from .verb_slots import interpret_verb_slots

_WORD = r"[A-Za-zÅÄÖåäöÉéÜü]+(?:-[A-Za-zÅÄÖåäöÉéÜü]+)*"
_PRESENT_ONLY_RE = re.compile(r"^pres\.$", re.IGNORECASE)
_SINGLE_FORM_RE = re.compile(rf"^{_WORD}$")
_LABEL_RE = re.compile(
    r"(?P<label>pres|pret|sup|imper|inf)\.\s*(?P<body>[^;]*)",
    re.IGNORECASE,
)
_FORM_RE = re.compile(_WORD)
_NON_FORM_WORDS = {
    "och",
    "ibl",
    "prov",
    "finl",
    "el",
    "vard",
    "åld",
    "obrukl",
    "saknas",
}
_LABEL_TO_SLOT = {
    "pres": "attested_present",
    "pret": "attested_preterite",
    "sup": "attested_supine",
    "imper": "attested_imperative",
    "inf": "attested_infinitive",
}


def _metadata(record: dict[str, Any], *, fallback_kind: str) -> dict[str, str]:
    return {
        "record_id": str(record.get("id") or record.get("subnr") or ""),
        "homonym_number": str(record.get("homonr") or ""),
        "ordkl": str(record.get("ordkl") or ""),
        "fallback_kind": fallback_kind,
    }


def _is_playable_lemma(lemma: str) -> bool:
    return bool(
        lemma
        and " " not in lemma
        and not lemma.startswith("-")
        and not lemma.endswith("-")
    )


def _explicit_labelled_forms(pattern: str) -> tuple[SlotForm, ...]:
    """Extract only forms explicitly governed by grammatical labels.

    Labels and usage markers are never emitted as words. A labelled segment
    contributes a form only when it contains an actual non-marker token. Thus
    ``sup. måst`` yields ``måst``, while ``pres. och pret.`` yields nothing.
    """
    forms: list[SlotForm] = []
    for match in _LABEL_RE.finditer(pattern):
        label = match.group("label").casefold()
        body = match.group("body")
        for token_match in _FORM_RE.finditer(body):
            token = token_match.group(0)
            folded = token.casefold()
            if folded in _NON_FORM_WORDS or folded in _LABEL_TO_SLOT:
                continue
            forms.append(
                SlotForm(
                    _LABEL_TO_SLOT[label],
                    token,
                    f"explicit_{label}",
                )
            )
    return tuple(forms)


def _attested_forms(
    record: dict[str, Any],
    lemma: str,
    pattern: str | None,
) -> tuple[SlotForm, ...] | None:
    """Return conservative SAOL-attested forms when no paradigm was parsed."""
    forms = [SlotForm("attested", lemma, "headword")]

    if pattern is None or _PRESENT_ONLY_RE.fullmatch(pattern):
        return tuple(forms)

    if _SINGLE_FORM_RE.fullmatch(pattern):
        forms.append(SlotForm("attested", pattern, "explicit_form"))
        return tuple(forms)

    labelled = _explicit_labelled_forms(pattern)
    if labelled:
        forms.extend(labelled)
        return tuple(forms)

    return None


def interpret_playable_verb_slots(record: dict[str, Any]) -> LexemeSlots | None:
    """Interpret a playable verb, preferring the strict shared parser.

    Multiword lemmas and affix entries are deliberately excluded before any
    parser is called. Residual rows then use the same narrow policy as the verb
    audit, keeping the canonical export and the analysis in agreement.
    """
    if str(record.get("upos", "")).upper() != "VERB":
        return None
    lemma = str(record.get("normaliserat_ord") or "").strip()
    if not _is_playable_lemma(lemma):
        return None

    parsed = interpret_verb_slots(record)
    if parsed is not None:
        return parsed

    residual = interpret_residual_verb_slots(record)
    if residual is not None:
        return residual

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
