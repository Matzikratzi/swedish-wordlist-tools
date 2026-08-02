from __future__ import annotations

from dataclasses import replace
from typing import Any

from .inflect import GeneratedEntry, GeneratedWordForm, normalise_pattern
from .msd import parse_msd

_CI = parse_msd("ci")
_SG_INDEF_GEN = parse_msd("sg indef gen")
_SG_DEF_NOM = parse_msd("sg def nom")
_SG_DEF_GEN = parse_msd("sg def gen")
_PL_INDEF_NOM = parse_msd("pl indef nom")
_PL_INDEF_GEN = parse_msd("pl indef gen")
_PL_DEF_NOM = parse_msd("pl def nom")
_PL_DEF_GEN = parse_msd("pl def gen")

_FULL_PARADIGM_PATTERNS = {
    "+en +er",
    "+en +ar",
    "+et +er",
    "+et; pl. +",
    "+n; pl. +",
    "+t +n",
    "+n +r",
    "+n +er",
}

_SINGULAR_ONLY_PATTERNS = {
    "+en",
    "+n",
    "+et",
    "+t",
}


def _genitive(form: str) -> str:
    """Return the ordinary Swedish genitive spelling."""
    return form if form.casefold().endswith(("s", "x", "z")) else form + "s"


def _attach_suffix(lemma: str, suffix: str) -> str:
    head, separator, tail = lemma.partition(" ")
    return head + suffix + (separator + tail if separator else "")


def _entry_from_singular_pattern(
    record: dict[str, Any], pattern: str, suffix: str
) -> GeneratedEntry | None:
    lemma = str(record.get("normaliserat_ord", "")).strip()
    if not lemma:
        return None
    return GeneratedEntry(
        lemma=lemma,
        pattern=pattern,
        word_forms=(
            GeneratedWordForm(lemma, _CI, "lemma"),
            GeneratedWordForm(_attach_suffix(lemma, suffix), _SG_DEF_NOM, "derived"),
        ),
        pattern_group=pattern,
    )


def _entry_from_full_pattern(
    record: dict[str, Any], pattern: str, singular_suffix: str, plural_suffix: str
) -> GeneratedEntry | None:
    lemma = str(record.get("normaliserat_ord", "")).strip()
    if not lemma:
        return None
    return GeneratedEntry(
        lemma=lemma,
        pattern=pattern,
        word_forms=(
            GeneratedWordForm(lemma, _CI, "lemma"),
            GeneratedWordForm(_attach_suffix(lemma, singular_suffix), _SG_DEF_NOM, "derived"),
            GeneratedWordForm(_attach_suffix(lemma, plural_suffix), _PL_INDEF_NOM, "derived"),
        ),
        pattern_group=pattern,
    )


def _definite_plural(lemma: str, plural: str, pattern: str) -> str:
    if pattern == "+et; pl. +":
        return lemma + "en"
    if pattern == "+n; pl. +":
        return plural + "na"
    if pattern == "+t +n":
        return plural + "a"
    return plural + "na"


def _form_for_msd(entry: GeneratedEntry, wanted: str) -> str | None:
    wanted_msd = parse_msd(wanted).casefold()
    for word_form in entry.word_forms:
        if word_form.msd is not None and word_form.msd.casefold() == wanted_msd:
            return word_form.written_form
    return None


def _key_forms(entry: GeneratedEntry) -> tuple[str | None, str | None, str | None]:
    lemma = _form_for_msd(entry, "ci") or entry.lemma
    singular_definite = _form_for_msd(entry, "sg def nom")
    plural_indefinite = _form_for_msd(entry, "pl indef nom")

    if entry.pattern == "+t +n" and len(entry.forms) >= 3:
        lemma, singular_definite, plural_indefinite = entry.forms[:3]

    return lemma, singular_definite, plural_indefinite


def _merge_forms(
    entry: GeneratedEntry,
    additions: tuple[GeneratedWordForm, ...],
) -> GeneratedEntry:
    seen: set[tuple[str, str | None]] = set()
    word_forms: list[GeneratedWordForm] = []
    for word_form in (*entry.word_forms, *additions):
        marker = (
            word_form.written_form,
            str(word_form.msd) if word_form.msd is not None else None,
        )
        if word_form.written_form and marker not in seen:
            seen.add(marker)
            word_forms.append(word_form)
    return replace(entry, word_forms=tuple(word_forms))


def _complete_singular_only(entry: GeneratedEntry) -> GeneratedEntry:
    lemma = _form_for_msd(entry, "ci") or entry.lemma
    singular_definite = _form_for_msd(entry, "sg def nom")
    if not lemma or not singular_definite:
        return entry

    additions = (
        GeneratedWordForm(lemma, _CI, "lemma"),
        GeneratedWordForm(_genitive(lemma), _SG_INDEF_GEN, "derived_genitive"),
        GeneratedWordForm(singular_definite, _SG_DEF_NOM, "derived"),
        GeneratedWordForm(_genitive(singular_definite), _SG_DEF_GEN, "derived_genitive"),
    )
    return _merge_forms(entry, additions)


def _complete_full_paradigm(entry: GeneratedEntry) -> GeneratedEntry:
    lemma, singular_definite, plural_indefinite = _key_forms(entry)
    if not lemma or not singular_definite or plural_indefinite is None:
        return entry

    plural_definite = _definite_plural(lemma, plural_indefinite, entry.pattern)
    additions = (
        GeneratedWordForm(lemma, _CI, "lemma"),
        GeneratedWordForm(_genitive(lemma), _SG_INDEF_GEN, "derived_genitive"),
        GeneratedWordForm(singular_definite, _SG_DEF_NOM, "derived"),
        GeneratedWordForm(_genitive(singular_definite), _SG_DEF_GEN, "derived_genitive"),
        GeneratedWordForm(plural_indefinite, _PL_INDEF_NOM, "derived"),
        GeneratedWordForm(_genitive(plural_indefinite), _PL_INDEF_GEN, "derived_genitive"),
        GeneratedWordForm(plural_definite, _PL_DEF_NOM, "derived_definite_plural"),
        GeneratedWordForm(_genitive(plural_definite), _PL_DEF_GEN, "derived_genitive"),
    )
    return _merge_forms(entry, additions)


def complete_noun_entry(
    record: dict[str, Any],
    entry: GeneratedEntry | None,
) -> GeneratedEntry | None:
    """Expand conservatively interpreted SAOL noun key forms."""
    if str(record.get("upos", "")).upper() != "NOUN":
        return entry

    pattern = normalise_pattern(record.get("text"))
    if pattern is None:
        return entry

    if entry is None and pattern == "+et +er":
        entry = _entry_from_full_pattern(record, pattern, "et", "er")
    elif entry is None and pattern == "+n; pl. +":
        entry = _entry_from_full_pattern(record, pattern, "n", "")
    elif entry is None and pattern == "+t":
        entry = _entry_from_singular_pattern(record, pattern, "t")
    if entry is None:
        return None

    if entry.pattern in _SINGULAR_ONLY_PATTERNS:
        return _complete_singular_only(entry)
    if entry.pattern in _FULL_PARADIGM_PATTERNS:
        return _complete_full_paradigm(entry)
    return entry
