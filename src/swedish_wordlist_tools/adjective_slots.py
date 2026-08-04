from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .saol_notation import normalize_notation, split_alternative_branches

HARD_CAP = 50
WORD = r"[a-zåäöéü]+"


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
        result: list[str] = []
        seen: set[str] = set()
        for form in self.forms:
            if form.written_form not in seen:
                result.append(form.written_form)
                seen.add(form.written_form)
        return tuple(result)


def _value(record: dict[str, Any], key: str) -> str:
    value = record.get(key)
    if value is None or str(value) == "(null)":
        return ""
    return str(value).strip()


def _deduplicate(forms: list[AdjectiveForm]) -> tuple[AdjectiveForm, ...]:
    result: list[AdjectiveForm] = []
    seen: set[tuple[str, str]] = set()
    for form in forms:
        marker = (form.written_form, form.slot)
        if marker not in seen:
            result.append(form)
            seen.add(marker)
    return tuple(result)


def _add_neuter_t(lemma: str) -> str:
    if lemma.endswith(("rd", "ld")):
        return lemma[:-1] + "t"
    if lemma.endswith("d"):
        return lemma[:-1] + "tt"
    return lemma + "t"


def _replace_final_component(lemma: str, replacement: str) -> str | None:
    replacement = replacement.lstrip("-")
    if not replacement or not replacement.isalpha():
        return None
    positions = [index for index, char in enumerate(lemma) if char == replacement[0]]
    if not positions:
        return None
    return lemma[: positions[-1]] + replacement


def _replace_suffix(lemma: str, old: str, new: str) -> str | None:
    if not old or not lemma.endswith(old):
        return None
    return lemma[: -len(old)] + new


def _resolve(lemma: str, token: str, *, neuter: bool = False) -> str | None:
    token = token.strip()
    if token == "+":
        return lemma
    if token == "+t" and neuter:
        return _add_neuter_t(lemma)
    if token == "+-t" and neuter:
        # reliabel -> reliabelt: remove nothing, append t. The '-' marks the
        # morpheme boundary, not a literal deletion amount.
        return lemma + "t"
    if token.startswith("+"):
        suffix = token[1:]
        return lemma + suffix if suffix.isalpha() else None
    if token.startswith("-"):
        return _replace_final_component(lemma, token)
    return token if token.isalpha() else None


def _slots(lemma: str, forms: list[AdjectiveForm], rule: str) -> AdjectiveSlots:
    return AdjectiveSlots(lemma, _deduplicate(forms), rule)


def _regular_patterns(lemma: str, text: str) -> AdjectiveSlots | None:
    table = {
        "+t +a": (_add_neuter_t(lemma), lemma + "a", "regular_t_a"),
        "n. +, +a": (lemma, lemma + "a", "unchanged_neuter_a"),
        "+tt +a": (lemma + "tt", lemma + "a", "regular_tt_a"),
        "+t +ma": (_add_neuter_t(lemma), lemma + "ma", "regular_t_ma"),
    }
    if text not in table:
        return None
    neuter, plural, rule = table[text]
    return _slots(lemma, [
        AdjectiveForm(lemma, "common_singular"),
        AdjectiveForm(neuter, "neuter_singular"),
        AdjectiveForm(plural, "definite_or_plural"),
    ], rule)


def _explicit_pair(lemma: str, text: str) -> AdjectiveSlots | None:
    match = re.fullmatch(rf"(?P<n>[+-]?{WORD}) (?P<p>[+-]?{WORD})", text)
    if not match:
        return None
    neuter = _resolve(lemma, match.group("n"), neuter=True)
    plural = _resolve(lemma, match.group("p"))
    if neuter is None or plural is None:
        return None
    return _slots(lemma, [
        AdjectiveForm(lemma, "common_singular"),
        AdjectiveForm(neuter, "neuter_singular"),
        AdjectiveForm(plural, "definite_or_plural"),
    ], "explicit_neuter_plural_pair")


def _limited(lemma: str, text: str) -> AdjectiveSlots | None:
    if text == "best.":
        return _slots(lemma, [AdjectiveForm(lemma, "definite_or_plural")], "labelled_limited_paradigm")
    match = re.fullmatch(rf"(?P<label>pl\.|mask\.|best\.) (?P<form>[+-]?{WORD})", text)
    if not match:
        return None
    form = _resolve(lemma, match.group("form"))
    if form is None:
        return None
    slot = "masculine_definite" if match.group("label") == "mask." else "definite_or_plural"
    return _slots(lemma, [
        AdjectiveForm(lemma, "common_singular"),
        AdjectiveForm(form, slot),
    ], "labelled_limited_paradigm")


def _single_slots(lemma: str, text: str) -> AdjectiveSlots | None:
    if text == "+t":
        return _slots(lemma, [AdjectiveForm(lemma, "common_singular"), AdjectiveForm(_add_neuter_t(lemma), "neuter_singular")], "neuter_only")
    if text == "n. +":
        return _slots(lemma, [AdjectiveForm(lemma, "common_singular"), AdjectiveForm(lemma, "neuter_singular")], "unchanged_neuter_only")
    match = re.fullmatch(rf"neutr\. \+; pl\. (?P<p>{WORD})", text)
    if match:
        return _slots(lemma, [
            AdjectiveForm(lemma, "common_singular"),
            AdjectiveForm(lemma, "neuter_singular"),
            AdjectiveForm(match.group("p"), "definite_or_plural"),
        ], "unchanged_neuter_explicit_plural")
    match = re.fullmatch(WORD, text)
    if match:
        return _slots(lemma, [AdjectiveForm(lemma, "common_singular"), AdjectiveForm(text, "definite_or_plural")], "explicit_single_additional_form")
    return None


def _plural_alternatives(lemma: str, text: str) -> AdjectiveSlots | None:
    match = re.fullmatch(rf"(?P<n>[+-]?{WORD}), best\. och: pl\. (?P<a>[+]?{WORD}|\+) el\. (?P<b>[+]?{WORD})", text)
    if not match:
        return None
    neuter = _resolve(lemma, match.group("n"), neuter=True)
    first = _resolve(lemma, match.group("a"))
    second = _resolve(lemma, match.group("b"))
    if None in {neuter, first, second}:
        return None
    rule = "labelled_plural_alternatives" if match.group("n").startswith("-") else "full_labelled_plural_alternatives"
    return _slots(lemma, [
        AdjectiveForm(lemma, "common_singular"),
        AdjectiveForm(neuter, "neuter_singular"),
        AdjectiveForm(first, "definite_or_plural"),
        AdjectiveForm(second, "definite_or_plural"),
    ], rule)


def _parallel(lemma: str, text: str) -> AdjectiveSlots | None:
    branches = split_alternative_branches(text)
    if len(branches) != 2:
        return None
    forms = [AdjectiveForm(lemma, "common_singular")]
    for branch in branches:
        match = re.fullmatch(rf"(?P<n>-?{WORD}) (?P<p>\+{WORD}|{WORD})", branch.text)
        if not match:
            return None
        neuter = _resolve(lemma, match.group("n"), neuter=True)
        if neuter is None:
            return None
        plural_token = match.group("p")
        if plural_token == "+e" and neuter.endswith("at"):
            common = neuter[:-2] + "ad"
            plural = common + "e"
            forms.append(AdjectiveForm(common, "common_singular"))
        elif plural_token.startswith("+"):
            return None
        else:
            plural = plural_token
        forms.extend((AdjectiveForm(neuter, "neuter_singular"), AdjectiveForm(plural, "definite_or_plural")))
    return _slots(lemma, forms, "parallel_alternative_paradigms")


def _generic_explicit_notation(lemma: str, text: str) -> AdjectiveSlots | None:
    """Parse remaining rows as slot sequences rather than word-specific cases."""
    # Explicit neuter plus optional comment plus added plural: perent [-en>t] +a
    match = re.fullmatch(rf"(?P<n>{WORD}) (?P<p>\+{WORD})", text)
    if match:
        plural = _resolve(lemma, match.group("p"))
        return _slots(lemma, [
            AdjectiveForm(lemma, "common_singular"),
            AdjectiveForm(match.group("n"), "neuter_singular"),
            AdjectiveForm(plural, "definite_or_plural"),
        ], "generic_explicit_slots")

    # Unchanged neuter with a fully written plural: n. +, justa
    match = re.fullmatch(rf"n\. \+, (?P<p>{WORD})", text)
    if match:
        return _slots(lemma, [
            AdjectiveForm(lemma, "common_singular"),
            AdjectiveForm(lemma, "neuter_singular"),
            AdjectiveForm(match.group("p"), "definite_or_plural"),
        ], "generic_explicit_slots")

    # Two alternative plural/definite forms: bemälda el. bemälta
    match = re.fullmatch(rf"(?P<a>{WORD}) el\. (?P<b>{WORD})", text)
    if match:
        return _slots(lemma, [
            AdjectiveForm(lemma, "common_singular"),
            AdjectiveForm(match.group("a"), "definite_or_plural"),
            AdjectiveForm(match.group("b"), "definite_or_plural"),
        ], "generic_explicit_slots")

    # Full positive and comparison sequence after bracket comments are gone.
    match = re.fullmatch(rf"(?P<n>{WORD}) (?P<p>{WORD}), (?P<c>{WORD}) (?P<s>{WORD})", text)
    if match:
        return _slots(lemma, [
            AdjectiveForm(lemma, "common_singular"),
            AdjectiveForm(match.group("n"), "neuter_singular"),
            AdjectiveForm(match.group("p"), "definite_or_plural"),
            AdjectiveForm(match.group("c"), "comparative"),
            AdjectiveForm(match.group("s"), "superlative"),
        ], "generic_explicit_slots")

    # Neuter followed by comparison alternatives: +t, trängre H +are, trängst H +ast
    match = re.fullmatch(rf"(?P<n>\+t), (?P<c>{WORD}) h (?P<ca>\+{WORD}), (?P<s>{WORD}) h (?P<sa>\+{WORD})", text)
    if match:
        values = [
            AdjectiveForm(lemma, "common_singular"),
            AdjectiveForm(_add_neuter_t(lemma), "neuter_singular"),
            AdjectiveForm(match.group("c"), "comparative"),
            AdjectiveForm(_resolve(lemma, match.group("ca")), "comparative"),
            AdjectiveForm(match.group("s"), "superlative"),
            AdjectiveForm(_resolve(lemma, match.group("sa")), "superlative"),
        ]
        return _slots(lemma, values, "generic_explicit_slots")

    # +-t reliabla (reliabel -> reliabelt, reliabla)
    match = re.fullmatch(rf"(?P<n>\+-t) (?P<p>{WORD})", text)
    if match:
        return _slots(lemma, [
            AdjectiveForm(lemma, "common_singular"),
            AdjectiveForm(_resolve(lemma, match.group("n"), neuter=True), "neuter_singular"),
            AdjectiveForm(match.group("p"), "definite_or_plural"),
        ], "generic_explicit_slots")

    # +t pluralA _ +t pluralB: infer the alternative common form from plural -a.
    branches = split_alternative_branches(text)
    if len(branches) == 2:
        forms = [AdjectiveForm(lemma, "common_singular")]
        for index, branch in enumerate(branches):
            match = re.fullmatch(rf"\+t (?P<p>{WORD})", branch.text)
            if not match or not match.group("p").endswith("a"):
                return None
            common = lemma if index == 0 else match.group("p")[:-1] + "el"
            forms.extend((
                AdjectiveForm(common, "common_singular"),
                AdjectiveForm(_add_neuter_t(common), "neuter_singular"),
                AdjectiveForm(match.group("p"), "definite_or_plural"),
            ))
        return _slots(lemma, forms, "generic_parallel_slots")
    return None


def _comparison(lemma: str, text: str) -> AdjectiveSlots | None:
    forms = [AdjectiveForm(lemma, "common_singular")]
    match = re.fullmatch(rf"komp\. (?P<c>\+?{WORD})(?: el\. (?P<ca>{WORD}))?, superl\. (?P<s>\+?{WORD})(?: el\. (?P<sa>{WORD}))?", text)
    if match:
        for name, slot in (("c", "comparative"), ("ca", "comparative"), ("s", "superlative"), ("sa", "superlative")):
            token = match.group(name)
            if token:
                forms.append(AdjectiveForm(_resolve(lemma, token), slot))
        return _slots(lemma, forms, "comparison_only")
    match = re.fullmatch(rf"\+t \+a, komp\. (?P<c>\+?{WORD}), superl\. (?P<s>\+?{WORD})(?: h (?P<sa>\+{WORD}))?", text)
    if match:
        forms.extend((AdjectiveForm(_add_neuter_t(lemma), "neuter_singular"), AdjectiveForm(lemma + "a", "definite_or_plural")))
        for name, slot in (("c", "comparative"), ("s", "superlative"), ("sa", "superlative")):
            token = match.group(name)
            if token:
                forms.append(AdjectiveForm(_resolve(lemma, token), slot))
        return _slots(lemma, forms, "positive_with_comparison")
    return None


def interpret_simple_adjective_slots(record: dict[str, Any]) -> AdjectiveSlots | None:
    lemma = _value(record, "normaliserat_ord").casefold()
    raw_text = _value(record, "text")
    text = normalize_notation(raw_text)
    if not lemma or " " in lemma or not lemma.isalpha():
        return None
    if len(raw_text) == HARD_CAP and ("komp." in text or "superl." in text):
        return None
    return (
        _regular_patterns(lemma, text)
        or _plural_alternatives(lemma, text)
        or _limited(lemma, text)
        or _parallel(lemma, text)
        or _comparison(lemma, text)
        or _single_slots(lemma, text)
        or _explicit_pair(lemma, text)
        or _generic_explicit_notation(lemma, text)
    )
