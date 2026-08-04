from __future__ import annotations

import re
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


def _add_neuter_t(lemma: str) -> str:
    """Apply common Swedish spelling changes before adjective neuter ``-t``."""
    if lemma.endswith("rd") or lemma.endswith("ld"):
        return lemma[:-1] + "t"
    if lemma.endswith("d"):
        return lemma[:-1] + "tt"
    return lemma + "t"


def _replace_final_component(lemma: str, replacement: str) -> str | None:
    """Apply SAOL's ``-form`` notation to the final matching component."""
    replacement = replacement.lstrip("-")
    if not replacement or not replacement.isalpha():
        return None
    anchor = replacement[0]
    positions = [index for index, char in enumerate(lemma) if char == anchor]
    if not positions:
        return None
    return lemma[: positions[-1]] + replacement


def _resolve_form_token(lemma: str, token: str, *, neuter: bool) -> str | None:
    """Resolve one exact SAOL form token without guessing omitted morphology."""
    if token == "+":
        return lemma
    if token == "+t" and neuter:
        return _add_neuter_t(lemma)
    if token.startswith("+"):
        suffix = token[1:]
        return _append(lemma, suffix) if suffix.isalpha() else None
    if token.startswith("-"):
        return _replace_final_component(lemma, token)
    return token if token.isalpha() else None


def _explicit_two_form_slots(lemma: str, text: str) -> AdjectiveSlots | None:
    """Parse exact neuter/plural pairs encoded as two form tokens.

    Accepted examples include ``-färgat +e``, ``-bundet -bundna``,
    ``+t -säkra``, ``absurt +a`` and ``bebott bebodda``. Labels,
    alternatives and comparison syntax remain outside this parser.
    """
    match = re.fullmatch(
        r"(?P<neuter>[+-]?[a-zåäöéü]+) (?P<plural>[+-]?[a-zåäöéü]+)",
        text,
    )
    if match is None:
        return None

    neuter = _resolve_form_token(lemma, match.group("neuter"), neuter=True)
    plural = _resolve_form_token(lemma, match.group("plural"), neuter=False)
    if neuter is None or plural is None:
        return None

    return AdjectiveSlots(
        lemma=lemma,
        forms=(
            AdjectiveForm(lemma, "common_singular"),
            AdjectiveForm(neuter, "neuter_singular"),
            AdjectiveForm(plural, "definite_or_plural"),
        ),
        rule="explicit_neuter_plural_pair",
    )


def _labelled_plural_alternatives(lemma: str, text: str) -> AdjectiveSlots | None:
    """Parse rows such as ``-blått, best. och: pl. + el. +a``.

    The row explicitly supplies one neuter form and two permitted definite or
    plural spellings. A bare ``+`` means that the lemma spelling is unchanged.
    """
    match = re.fullmatch(
        r"(?P<neuter>-[a-zåäöéü]+), best\. och: pl\. "
        r"(?P<plural1>\+|\+[a-zåäöéü]+) el\. (?P<plural2>\+[a-zåäöéü]+)",
        text,
    )
    if match is None:
        return None

    neuter = _resolve_form_token(lemma, match.group("neuter"), neuter=True)
    plural1 = _resolve_form_token(lemma, match.group("plural1"), neuter=False)
    plural2 = _resolve_form_token(lemma, match.group("plural2"), neuter=False)
    if neuter is None or plural1 is None or plural2 is None:
        return None

    return AdjectiveSlots(
        lemma=lemma,
        forms=(
            AdjectiveForm(lemma, "common_singular"),
            AdjectiveForm(neuter, "neuter_singular"),
            AdjectiveForm(plural1, "definite_or_plural"),
            AdjectiveForm(plural2, "definite_or_plural_alternative"),
        ),
        rule="labelled_plural_alternatives",
    )


def interpret_simple_adjective_slots(record: dict[str, Any]) -> AdjectiveSlots | None:
    """Interpret exact, high-confidence SAOL14 adjective patterns.

    Comparison and missing text remain outside this stage. Exact form notation
    and narrowly defined labels are accepted when every resulting spelling is
    explicitly encoded on the SAOL row.
    """
    lemma = _value(record, "normaliserat_ord").casefold()
    text = " ".join(_value(record, "text").split()).casefold()
    if not lemma or " " in lemma or not lemma.isalpha():
        return None

    forms: list[AdjectiveForm] = [AdjectiveForm(lemma, "common_singular")]
    rule = ""

    if text == "+t +a":
        forms.extend((
            AdjectiveForm(_add_neuter_t(lemma), "neuter_singular"),
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
            AdjectiveForm(_add_neuter_t(lemma), "neuter_singular"),
            AdjectiveForm(_append(lemma, "ma"), "definite_or_plural"),
        ))
        rule = "regular_t_ma"
    else:
        return (
            _labelled_plural_alternatives(lemma, text)
            or _explicit_two_form_slots(lemma, text)
        )

    unique: list[AdjectiveForm] = []
    seen: set[tuple[str, str]] = set()
    for form in forms:
        marker = (form.written_form, form.slot)
        if marker not in seen:
            unique.append(form)
            seen.add(marker)
    return AdjectiveSlots(lemma=lemma, forms=tuple(unique), rule=rule)
