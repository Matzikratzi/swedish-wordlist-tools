from __future__ import annotations

import re
from typing import Any

from .inflect import normalise_pattern
from .lexeme_slots import LexemeSlots, SlotForm, build_lexeme_slots

_WORD = r"[A-Za-zÅÄÖåäöÉéÜü]+"
_SINGLE_EXPLICIT_RE = re.compile(rf"^(?P<form>{_WORD})$")
_PRESENT_ONLY_RE = re.compile(r"^pres\.$", re.IGNORECASE)
_PRESENT_OCCASIONAL_RE = re.compile(rf"^pres\.\s+ibl\.\s+(?P<form>{_WORD})$", re.IGNORECASE)
_DEFECTIVE_LABELLED_RE = re.compile(
    rf"^pres\.\s+och:\s+pret\.;\s+sup\.\s+(?P<supine>{_WORD});(?:\s+.*)?$",
    re.IGNORECASE,
)


def _value(record: dict[str, Any], key: str) -> str:
    value = record.get(key)
    if value is None or str(value) == "(null)":
        return ""
    return str(value).strip()


def _build(
    record: dict[str, Any],
    lemma: str,
    pattern: str,
    forms: tuple[SlotForm, ...],
) -> LexemeSlots:
    return build_lexeme_slots(
        lemma=lemma,
        upos="VERB",
        notation=pattern,
        forms=forms,
        metadata={
            "record_id": str(record.get("id") or record.get("subnr") or ""),
            "homonym_number": _value(record, "homonr"),
            "stycke": _value(record, "stycke"),
            "ordkl": _value(record, "ordkl"),
            "residual_policy": "true",
        },
    )


def interpret_residual_verb_slots(record: dict[str, Any]) -> LexemeSlots | None:
    """Interpret conservative residual SAOL verb rows.

    This is intentionally narrow. It keeps only forms that are explicit in the
    row, or the lemma itself when the row gives no inflection text or only a
    tense label. It does not infer a full paradigm.
    """

    if str(record.get("upos", "")).upper() != "VERB":
        return None
    lemma = _value(record, "normaliserat_ord")
    if not lemma or " " in lemma or lemma.startswith("-") or lemma.endswith("-"):
        return None

    raw_text = _value(record, "text")
    if not raw_text:
        return _build(
            record,
            lemma,
            "",
            (SlotForm("infinitive", lemma, "lemma"),),
        )

    pattern = normalise_pattern(raw_text)
    if pattern is None:
        return None

    if _PRESENT_ONLY_RE.fullmatch(pattern):
        return _build(
            record,
            lemma,
            pattern,
            (
                SlotForm("infinitive", lemma, "lemma"),
                SlotForm("present", lemma, "pres."),
            ),
        )

    match = _PRESENT_OCCASIONAL_RE.fullmatch(pattern)
    if match:
        occasional = match.group("form")
        return _build(
            record,
            lemma,
            pattern,
            (
                SlotForm("infinitive", lemma, "lemma"),
                SlotForm("present", lemma, "pres."),
                SlotForm("present", occasional, occasional),
            ),
        )

    match = _DEFECTIVE_LABELLED_RE.fullmatch(pattern)
    if match:
        supine = match.group("supine")
        return _build(
            record,
            lemma,
            pattern,
            (
                SlotForm("infinitive", lemma, "lemma"),
                SlotForm("present", lemma, "pres."),
                SlotForm("preterite", lemma, "pret."),
                SlotForm("supine", supine, supine),
            ),
        )

    match = _SINGLE_EXPLICIT_RE.fullmatch(pattern)
    if match:
        explicit = match.group("form")
        return _build(
            record,
            lemma,
            pattern,
            (
                SlotForm("infinitive", lemma, "lemma"),
                SlotForm("explicit_additional", explicit, explicit),
            ),
        )

    return None
