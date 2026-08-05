from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .saol_notation import normalize_notation

HARD_CAP = 50
W = r"[a-zåäöéü]+"


@dataclass(frozen=True)
class AdjectiveForm:
    written_form: str
    slot: str
    provenance: str = "row"


@dataclass(frozen=True)
class UsageRestriction:
    scope: str
    label: str
    forms: tuple[str, ...] = ()


@dataclass(frozen=True)
class AdjectiveSlots:
    lemma: str
    forms: tuple[AdjectiveForm, ...]
    rule: str
    restrictions: tuple[UsageRestriction, ...] = ()

    def written_forms(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(form.written_form for form in self.forms))


def _value(record: dict[str, Any], key: str) -> str:
    value = record.get(key)
    return "" if value is None or str(value) == "(null)" else str(value).strip()


def _neuter_t(word: str) -> str:
    if word.endswith(("rd", "ld")):
        return word[:-1] + "t"
    if word.endswith("d"):
        return word[:-1] + "tt"
    return word + "t"


def _replace_tail(word: str, tail: str) -> str | None:
    tail = tail.lstrip("-")
    if not tail or not tail.isalpha():
        return None
    positions = [i for i, char in enumerate(word) if char == tail[0]]
    return None if not positions else word[: positions[-1]] + tail


def _resolve(lemma: str, token: str, *, neuter: bool = False) -> str | None:
    if token == "+":
        return lemma
    if token == "+t" and neuter:
        return _neuter_t(lemma)
    if token == "+-t" and neuter:
        return lemma + "t"
    if token.startswith("+"):
        return lemma + token[1:] if token[1:].isalpha() else None
    if token.startswith("-"):
        return _replace_tail(lemma, token)
    return token if token.isalpha() else None


def _slots(
    lemma: str,
    values: list[tuple[str | None, str]],
    rule: str,
    restrictions: tuple[UsageRestriction, ...] = (),
) -> AdjectiveSlots | None:
    if any(value is None for value, _ in values):
        return None
    forms: list[AdjectiveForm] = []
    seen: set[tuple[str, str]] = set()
    for value, slot in values:
        assert value is not None
        marker = (value, slot)
        if marker not in seen:
            forms.append(AdjectiveForm(value, slot))
            seen.add(marker)
    return AdjectiveSlots(lemma, tuple(forms), rule, restrictions)


def _regular(lemma: str, text: str) -> AdjectiveSlots | None:
    patterns = {
        "+t +a": (_neuter_t(lemma), lemma + "a", "regular_t_a"),
        "n. +, +a": (lemma, lemma + "a", "unchanged_neuter_a"),
        "+tt +a": (lemma + "tt", lemma + "a", "regular_tt_a"),
        "+t +ma": (_neuter_t(lemma), lemma + "ma", "regular_t_ma"),
    }
    if text not in patterns:
        return None
    n, p, rule = patterns[text]
    return _slots(lemma, [(lemma, "common_singular"), (n, "neuter_singular"), (p, "definite_or_plural")], rule)


def _known_structures(lemma: str, text: str) -> AdjectiveSlots | None:
    if text == "+t":
        return _slots(lemma, [(lemma, "common_singular"), (_neuter_t(lemma), "neuter_singular")], "neuter_only")
    if text == "n. +":
        return _slots(lemma, [(lemma, "common_singular"), (lemma, "neuter_singular")], "unchanged_neuter_only")
    if text == "best.":
        return _slots(lemma, [(lemma, "definite_or_plural")], "labelled_limited_paradigm")

    m = re.fullmatch(rf"(?P<label>pl\.|mask\.|best\.) (?P<f>[+-]?{W})", text)
    if m:
        slot = "masculine_definite" if m.group("label") == "mask." else "definite_or_plural"
        return _slots(lemma, [(lemma, "common_singular"), (_resolve(lemma, m.group("f")), slot)], "labelled_limited_paradigm")

    m = re.fullmatch(rf"neutr\. \+; pl\. (?P<p>{W})", text)
    if m:
        return _slots(lemma, [(lemma, "common_singular"), (lemma, "neuter_singular"), (m.group("p"), "definite_or_plural")], "unchanged_neuter_explicit_plural")

    m = re.fullmatch(rf"(?P<n>[+-]?{W}), best\. och: pl\. (?P<a>\+|\+?{W}) el\. (?P<b>\+?{W})", text)
    if m:
        rule = "labelled_plural_alternatives" if m.group("n").startswith("-") else "full_labelled_plural_alternatives"
        return _slots(lemma, [(lemma, "common_singular"), (_resolve(lemma, m.group("n"), neuter=True), "neuter_singular"), (_resolve(lemma, m.group("a")), "definite_or_plural"), (_resolve(lemma, m.group("b")), "definite_or_plural")], rule)

    m = re.fullmatch(rf"(?P<n>[+-]?{W}) (?P<p>[+-]?{W})", text)
    if m:
        return _slots(lemma, [(lemma, "common_singular"), (_resolve(lemma, m.group("n"), neuter=True), "neuter_singular"), (_resolve(lemma, m.group("p")), "definite_or_plural")], "explicit_neuter_plural_pair")

    m = re.fullmatch(W, text)
    if m:
        return _slots(lemma, [(lemma, "common_singular"), (text, "definite_or_plural")], "explicit_single_additional_form")
    return None


def _parallel(lemma: str, text: str) -> AdjectiveSlots | None:
    branches = text.split(" _ ")
    if len(branches) != 2:
        return None
    values: list[tuple[str | None, str]] = [(lemma, "common_singular")]

    parsed: list[tuple[str, str, str | None]] = []
    for branch in branches:
        m = re.fullmatch(rf"(?P<n>-?{W}) (?P<p>\+e|{W})", branch)
        if not m:
            parsed = []
            break
        neuter = _resolve(lemma, m.group("n"), neuter=True)
        if neuter is None:
            return None
        common = neuter[:-2] + "ad" if m.group("p") == "+e" and neuter.endswith("at") else None
        plural = common + "e" if common else m.group("p")
        parsed.append((neuter, plural, common))
    if parsed:
        for neuter, plural, common in parsed:
            if common:
                values.append((common, "common_singular"))
            values.extend(((neuter, "neuter_singular"), (plural, "definite_or_plural")))
        return _slots(lemma, values, "parallel_alternative_paradigms")

    plurals: list[str] = []
    for branch in branches:
        m = re.fullmatch(rf"\+t (?P<p>{W})", branch)
        if not m:
            return None
        plurals.append(m.group("p"))
    alt_plural = plurals[1]
    if not alt_plural.endswith("bla"):
        return None
    alt_common = alt_plural[:-3] + "bel"
    return _slots(lemma, [
        (lemma, "common_singular"), (_neuter_t(lemma), "neuter_singular"), (plurals[0], "definite_or_plural"),
        (alt_common, "common_singular"), (_neuter_t(alt_common), "neuter_singular"), (alt_plural, "definite_or_plural"),
    ], "generic_parallel_slots")


def _comparison(lemma: str, text: str) -> AdjectiveSlots | None:
    m = re.fullmatch(rf"komp\. (?P<c>\+?{W})(?: el\. (?P<ca>{W}))?, superl\. (?P<s>\+?{W})(?: el\. (?P<sa>{W}))?", text)
    if m:
        values: list[tuple[str | None, str]] = [(lemma, "common_singular")]
        for name, slot in (("c", "comparative"), ("ca", "comparative"), ("s", "superlative"), ("sa", "superlative")):
            if m.group(name):
                values.append((_resolve(lemma, m.group(name)), slot))
        return _slots(lemma, values, "comparison_only")

    m = re.fullmatch(rf"\+t \+a, komp\. (?P<c>\+?{W}), superl\. (?P<s>\+?{W})(?: h (?P<sa>\+{W}))?", text)
    if m:
        values = [(lemma, "common_singular"), (_neuter_t(lemma), "neuter_singular"), (lemma + "a", "definite_or_plural"), (_resolve(lemma, m.group("c")), "comparative"), (_resolve(lemma, m.group("s")), "superlative")]
        if m.group("sa"):
            values.append((_resolve(lemma, m.group("sa")), "superlative"))
        return _slots(lemma, values, "positive_with_comparison")

    m = re.fullmatch(rf"(?P<n>{W}) (?P<p>{W}), (?P<c>{W}) (?P<s>{W})", text)
    if m:
        return _slots(lemma, [(lemma, "common_singular"), (m.group("n"), "neuter_singular"), (m.group("p"), "definite_or_plural"), (m.group("c"), "comparative"), (m.group("s"), "superlative")], "generic_explicit_slots")

    m = re.fullmatch(rf"\+t, (?P<c>{W}) h (?P<ca>\+{W}), (?P<s>{W}) h (?P<sa>\+{W})", text)
    if m:
        return _slots(lemma, [(lemma, "common_singular"), (_neuter_t(lemma), "neuter_singular"), (m.group("c"), "comparative"), (_resolve(lemma, m.group("ca")), "comparative"), (m.group("s"), "superlative"), (_resolve(lemma, m.group("sa")), "superlative")], "generic_explicit_slots")

    m = re.fullmatch(rf"\+t (?P<p>\+a|{W}), (?P<c>{W}) (?P<s>{W})", text)
    if m:
        plural = _resolve(lemma, m.group("p"))
        return _slots(lemma, [
            (lemma, "common_singular"),
            (_neuter_t(lemma), "neuter_singular"),
            (plural, "definite_or_plural"),
            (m.group("c"), "comparative"),
            (m.group("s"), "superlative"),
        ], "positive_with_explicit_comparison")
    return None


def _usage_restricted(lemma: str, text: str) -> AdjectiveSlots | None:
    m = re.fullmatch(rf"n\. sing\. obest\. (?P<label>obrukl\.|undviks:)(?:, (?P<p>-?{W}))?", text)
    if m:
        values: list[tuple[str | None, str]] = [(lemma, "common_singular")]
        resolved = _resolve(lemma, m.group("p")) if m.group("p") else None
        if resolved:
            values.append((resolved, "definite_or_plural"))
        label = "uncommon" if m.group("label") == "obrukl." else "avoided"
        return _slots(
            lemma,
            values,
            "usage_restricted_explicit_slots",
            (UsageRestriction("neuter_singular", label),),
        )

    m = re.fullmatch(rf"neutr\. undviks:, (?P<p>[+-]?{W})", text)
    if m:
        plural = _resolve(lemma, m.group("p"))
        return _slots(
            lemma,
            [(lemma, "common_singular"), (plural, "definite_or_plural")],
            "usage_restricted_explicit_slots",
            (UsageRestriction("neuter_singular", "avoided"),),
        )

    m = re.fullmatch(rf"mest: oböjl\., best\. och: pl\. ibl\. (?P<p>{W})", text)
    if m:
        plural = m.group("p")
        return _slots(
            lemma,
            [(lemma, "common_singular"), (plural, "definite_or_plural")],
            "usage_restricted_explicit_slots",
            (
                UsageRestriction("paradigm", "mostly_uninflected"),
                UsageRestriction("definite_or_plural", "occasional", (plural,)),
            ),
        )
    return None


def _generic(lemma: str, text: str) -> AdjectiveSlots | None:
    m = re.fullmatch(rf"n\. \+, (?P<p>{W})", text)
    if m:
        return _slots(lemma, [(lemma, "common_singular"), (lemma, "neuter_singular"), (m.group("p"), "definite_or_plural")], "generic_explicit_slots")
    m = re.fullmatch(rf"n\. (?P<n>{W})", text)
    if m:
        return _slots(lemma, [(lemma, "common_singular"), (m.group("n"), "neuter_singular")], "generic_explicit_slots")
    m = re.fullmatch(rf"(?P<a>{W}) el\. (?P<b>{W})", text)
    if m:
        return _slots(lemma, [(lemma, "common_singular"), (m.group("a"), "definite_or_plural"), (m.group("b"), "definite_or_plural")], "generic_explicit_slots")
    m = re.fullmatch(rf"(?P<n>{W}) (?P<p>\+{W})", text)
    if m:
        return _slots(lemma, [(lemma, "common_singular"), (m.group("n"), "neuter_singular"), (_resolve(lemma, m.group("p")), "definite_or_plural")], "generic_explicit_slots")
    m = re.fullmatch(rf"\+-t (?P<p>{W})", text)
    if m:
        return _slots(lemma, [(lemma, "common_singular"), (lemma + "t", "neuter_singular"), (m.group("p"), "definite_or_plural")], "generic_explicit_slots")

    m = re.fullmatch(rf"(?P<n>{W}), best\. (?P<masc>{W}) (?P<definite>{W}); pl\. (?P<plural>{W}); (?P<c>{W}) (?P<s>{W})", text)
    if m:
        return _slots(lemma, [
            (lemma, "common_singular"),
            (m.group("n"), "neuter_singular"),
            (m.group("masc"), "masculine_definite"),
            (m.group("definite"), "definite_or_plural"),
            (m.group("plural"), "definite_or_plural"),
            (m.group("c"), "comparative"),
            (m.group("s"), "superlative"),
        ], "generic_labelled_full_paradigm")

    m = re.fullmatch(rf"(?P<masc>{W}), vard\. superl\. (?P<s>{W})", text)
    if m:
        return _slots(lemma, [
            (lemma, "common_singular"),
            (m.group("masc"), "masculine_definite"),
            (m.group("s"), "superlative"),
        ], "generic_labelled_partial_paradigm")
    return None


def interpret_simple_adjective_slots(record: dict[str, Any]) -> AdjectiveSlots | None:
    lemma = _value(record, "normaliserat_ord").casefold()
    raw_text = _value(record, "text")
    text = normalize_notation(raw_text)
    if not lemma or " " in lemma or not lemma.isalpha():
        return None
    if len(raw_text) == HARD_CAP and ("komp." in text or "superl." in text):
        return None
    return _regular(lemma, text) or _parallel(lemma, text) or _comparison(lemma, text) or _usage_restricted(lemma, text) or _generic(lemma, text) or _known_structures(lemma, text)
