from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

HARD_CAP = 50


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
    if lemma.endswith("rd") or lemma.endswith("ld"):
        return lemma[:-1] + "t"
    if lemma.endswith("d"):
        return lemma[:-1] + "tt"
    return lemma + "t"


def _replace_final_component(lemma: str, replacement: str) -> str | None:
    replacement = replacement.lstrip("-")
    if not replacement or not replacement.isalpha():
        return None
    anchor = replacement[0]
    positions = [index for index, char in enumerate(lemma) if char == anchor]
    if not positions:
        return None
    return lemma[: positions[-1]] + replacement


def _resolve_form_token(lemma: str, token: str, *, neuter: bool = False) -> str | None:
    token = token.strip()
    if token == "+" and not neuter:
        return lemma
    if token == "+t" and neuter:
        return _add_neuter_t(lemma)
    if token.startswith("+"):
        suffix = token[1:]
        return _append(lemma, suffix) if suffix.isalpha() else None
    if token.startswith("-"):
        return _replace_final_component(lemma, token)
    return token if token.isalpha() else None


def _deduplicate(forms: list[AdjectiveForm]) -> tuple[AdjectiveForm, ...]:
    result: list[AdjectiveForm] = []
    seen: set[tuple[str, str]] = set()
    for form in forms:
        marker = (form.written_form, form.slot)
        if marker not in seen:
            result.append(form)
            seen.add(marker)
    return tuple(result)


def _explicit_two_form_slots(lemma: str, text: str) -> AdjectiveSlots | None:
    match = re.fullmatch(
        r"(?P<neuter>[+-]?[a-zåäöéü]+) (?P<plural>[+-]?[a-zåäöéü]+)", text
    )
    if match is None:
        return None
    neuter = _resolve_form_token(lemma, match.group("neuter"), neuter=True)
    plural = _resolve_form_token(lemma, match.group("plural"))
    if neuter is None or plural is None:
        return None
    return AdjectiveSlots(
        lemma,
        (
            AdjectiveForm(lemma, "common_singular"),
            AdjectiveForm(neuter, "neuter_singular"),
            AdjectiveForm(plural, "definite_or_plural"),
        ),
        "explicit_neuter_plural_pair",
    )


def _labelled_plural_alternatives(lemma: str, text: str) -> AdjectiveSlots | None:
    match = re.fullmatch(
        r"(?P<neuter>-[a-zåäöéü]+), best\. och: pl\. (?P<first>\+) el\. (?P<second>\+[a-zåäöéü]+)",
        text,
    )
    if match is None:
        return None
    neuter = _resolve_form_token(lemma, match.group("neuter"), neuter=True)
    first = _resolve_form_token(lemma, match.group("first"))
    second = _resolve_form_token(lemma, match.group("second"))
    if neuter is None or first is None or second is None:
        return None
    return AdjectiveSlots(
        lemma,
        _deduplicate([
            AdjectiveForm(lemma, "common_singular"),
            AdjectiveForm(neuter, "neuter_singular"),
            AdjectiveForm(first, "definite_or_plural"),
            AdjectiveForm(second, "definite_or_plural"),
        ]),
        "labelled_plural_alternatives",
    )


def _labelled_limited_slots(lemma: str, text: str) -> AdjectiveSlots | None:
    """Parse rows that explicitly expose only plural, definite or masculine forms."""
    if text == "best.":
        return AdjectiveSlots(
            lemma,
            (AdjectiveForm(lemma, "definite_or_plural"),),
            "labelled_limited_paradigm",
        )

    match = re.fullmatch(r"(?P<label>pl\.|mask\.|best\.) (?P<form>[+-]?[a-zåäöéü]+)", text)
    if match is None:
        return None
    form = _resolve_form_token(lemma, match.group("form"))
    if form is None:
        return None
    slot = {
        "pl.": "definite_or_plural",
        "mask.": "masculine_definite",
        "best.": "definite_or_plural",
    }[match.group("label")]
    return AdjectiveSlots(
        lemma,
        _deduplicate([
            AdjectiveForm(lemma, "common_singular"),
            AdjectiveForm(form, slot),
        ]),
        "labelled_limited_paradigm",
    )


def _comparison_slots(lemma: str, text: str) -> AdjectiveSlots | None:
    forms: list[AdjectiveForm] = [AdjectiveForm(lemma, "common_singular")]
    match = re.fullmatch(
        r"komp\. (?P<comparative>[+]?[a-zåäöéü]+)(?: el\. (?P<comparative_alt>[a-zåäöéü]+))?, "
        r"superl\. (?P<superlative>[+]?[a-zåäöéü]+)(?: el\. (?P<superlative_alt>[a-zåäöéü]+))?",
        text,
    )
    if match:
        for name, slot in (("comparative", "comparative"), ("comparative_alt", "comparative"), ("superlative", "superlative"), ("superlative_alt", "superlative")):
            token = match.group(name)
            if token:
                resolved = _resolve_form_token(lemma, token)
                if resolved is None:
                    return None
                forms.append(AdjectiveForm(resolved, slot))
        return AdjectiveSlots(lemma, _deduplicate(forms), "comparison_only")

    match = re.fullmatch(
        r"\+t \+a, komp\. (?P<comparative>[+]?[a-zåäöéü]+), superl\. (?P<superlative>[+]?[a-zåäöéü]+)(?: h (?P<superlative_alt>\+[a-zåäöéü]+))?",
        text,
    )
    if match:
        forms.extend((AdjectiveForm(_add_neuter_t(lemma), "neuter_singular"), AdjectiveForm(_append(lemma, "a"), "definite_or_plural")))
        for name, slot in (("comparative", "comparative"), ("superlative", "superlative"), ("superlative_alt", "superlative")):
            token = match.group(name)
            if token:
                resolved = _resolve_form_token(lemma, token)
                if resolved is None:
                    return None
                forms.append(AdjectiveForm(resolved, slot))
        return AdjectiveSlots(lemma, _deduplicate(forms), "positive_with_comparison")

    match = re.fullmatch(
        r"(?P<neuter>[+-]?[a-zåäöéü]+) (?P<plural>[+-]?[a-zåäöéü]+), (?P<comparative>[a-zåäöéü]+) (?P<superlative>[a-zåäöéü]+)",
        text,
    )
    if match:
        neuter = _resolve_form_token(lemma, match.group("neuter"), neuter=True)
        plural = _resolve_form_token(lemma, match.group("plural"))
        if neuter is None or plural is None:
            return None
        forms.extend((AdjectiveForm(neuter, "neuter_singular"), AdjectiveForm(plural, "definite_or_plural"), AdjectiveForm(match.group("comparative"), "comparative"), AdjectiveForm(match.group("superlative"), "superlative")))
        return AdjectiveSlots(lemma, _deduplicate(forms), "explicit_positive_and_comparison")
    return None


def interpret_simple_adjective_slots(record: dict[str, Any]) -> AdjectiveSlots | None:
    lemma = _value(record, "normaliserat_ord").casefold()
    raw_text = _value(record, "text")
    text = " ".join(raw_text.split()).casefold()
    if not lemma or " " in lemma or not lemma.isalpha():
        return None
    if len(raw_text) == HARD_CAP and ("komp." in text or "superl." in text):
        return None

    forms: list[AdjectiveForm] = [AdjectiveForm(lemma, "common_singular")]
    if text == "+t +a":
        forms.extend((AdjectiveForm(_add_neuter_t(lemma), "neuter_singular"), AdjectiveForm(_append(lemma, "a"), "definite_or_plural")))
        return AdjectiveSlots(lemma, _deduplicate(forms), "regular_t_a")
    if text == "n. +, +a":
        forms.extend((AdjectiveForm(lemma, "neuter_singular"), AdjectiveForm(_append(lemma, "a"), "definite_or_plural")))
        return AdjectiveSlots(lemma, _deduplicate(forms), "unchanged_neuter_a")
    if text == "+tt +a":
        forms.extend((AdjectiveForm(_append(lemma, "tt"), "neuter_singular"), AdjectiveForm(_append(lemma, "a"), "definite_or_plural")))
        return AdjectiveSlots(lemma, _deduplicate(forms), "regular_tt_a")
    if text == "+t +ma":
        forms.extend((AdjectiveForm(_add_neuter_t(lemma), "neuter_singular"), AdjectiveForm(_append(lemma, "ma"), "definite_or_plural")))
        return AdjectiveSlots(lemma, _deduplicate(forms), "regular_t_ma")
    return (
        _labelled_plural_alternatives(lemma, text)
        or _labelled_limited_slots(lemma, text)
        or _comparison_slots(lemma, text)
        or _explicit_two_form_slots(lemma, text)
    )
