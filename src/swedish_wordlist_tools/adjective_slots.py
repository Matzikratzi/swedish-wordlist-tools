from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AdjectiveForm:
    written_form: str
    slot: str
    provenance: str = "row"


@dataclass(frozen=True)
class AdjectiveSlots:
    lemma: str
    forms: tuple[AdjectiveForm, ...]
    rule: str

    def written_forms(self) -> tuple[str, ...]:
        return tuple(form.written_form for form in self.forms)


def _value(record: dict[str, Any], key: str) -> str:
    value = record.get(key)
    if value is None or str(value) == "(null)":
        return ""
    return str(value).strip()


def _append(lemma: str, suffix: str) -> str:
    return lemma + suffix


def interpret_simple_adjective_slots(record: dict[str, Any]) -> AdjectiveSlots | None:
    """Interpret only exact, high-confidence SAOL14 adjective patterns.

    This first stage deliberately handles only the four dominant regular rows.
    Replacement notation, comparison, participial patterns and missing text are
    left for later analysis rather than guessed.
    """
    lemma = _value(record, "normaliserat_ord").casefold()
    text = " ".join(_value(record, "text").split())
    if not lemma or " " in lemma or not lemma.isalpha():
        return None

    forms: list[AdjectiveForm] = [AdjectiveForm(lemma, "common_singular")]
    rule = ""

    if text == "+t +a":
        forms.extend((
            AdjectiveForm(_append(lemma, "t"), "neuter_singular"),
            AdjectiveForm(_append(lemma, "a"), "definite_or_plural"),
        ))
        rule = "regular_t_a"
    elif text == "n. +, +a":
        forms.extend((
            AdjectiveForm(lemma, "neuter_singular"),
            AdjectiveForm(_append(lemma, "a"), "definite_or_plural"),
        ))
        rule = "unchanged_neuter_a"
    elif text == "+tt +a":
        forms.extend((
            AdjectiveForm(_append(lemma, "tt"), "neuter_singular"),
            AdjectiveForm(_append(lemma, "a"), "definite_or_plural"),
        ))
        rule = "regular_tt_a"
    elif text == "+t +ma":
        forms.extend((
            AdjectiveForm(_append(lemma, "t"), "neuter_singular"),
            AdjectiveForm(_append(lemma, "ma"), "definite_or_plural"),
        ))
        rule = "regular_t_ma"
    else:
        return None

    # A form may occupy two grammatical slots; the game export only needs the
    # spelling, while the slot model keeps the interpretation explicit.
    unique: list[AdjectiveForm] = []
    seen: set[tuple[str, str]] = set()
    for form in forms:
        marker = (form.written_form, form.slot)
        if marker not in seen:
            unique.append(form)
            seen.add(marker)
    return AdjectiveSlots(lemma=lemma, forms=tuple(unique), rule=rule)
