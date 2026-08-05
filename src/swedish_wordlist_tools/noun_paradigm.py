from __future__ import annotations

from dataclasses import replace
from typing import Any

from .inflect import GeneratedEntry, GeneratedWordForm
from .msd import parse_msd

_CI = parse_msd("ci")
_SG_INDEF_GEN = parse_msd("sg indef gen")
_SG_DEF_NOM = parse_msd("sg def nom")
_SG_DEF_GEN = parse_msd("sg def gen")
_PL_INDEF_NOM = parse_msd("pl indef nom")
_PL_INDEF_GEN = parse_msd("pl indef gen")
_PL_DEF_NOM = parse_msd("pl def nom")
_PL_DEF_GEN = parse_msd("pl def gen")

_SUPPORTED_PATTERNS = {
    "+en +er",
    "+en +ar",
    "+et; pl. +",
    "+n +r",
    "+n +er",
}


def _genitive(form: str) -> str:
    """Return the ordinary Swedish genitive spelling.

    Words ending in s, x or z have an unmarked genitive in Swedish spelling.
    """
    return form if form.casefold().endswith(("s", "x", "z")) else form + "s"


def _definite_plural(lemma: str, plural: str, pattern: str) -> str:
    if pattern == "+et; pl. +":
        return lemma + "en"
    return plural + "na"


def _form_for_msd(entry: GeneratedEntry, wanted: str) -> str | None:
    wanted_msd = parse_msd(wanted).casefold()
    for word_form in entry.word_forms:
        if word_form.msd is not None and word_form.msd.casefold() == wanted_msd:
            return word_form.written_form
    return None


def complete_noun_entry(record: dict[str, Any], entry: GeneratedEntry | None) -> GeneratedEntry | None:
    """Expand safe SAOL noun key forms to a complete nominal paradigm.

    This first implementation is deliberately conservative. It only handles
    common patterns where the existing SAOL parser has typed the citation form,
    definite singular and indefinite plural. Unsupported and singular-only
    patterns are returned unchanged.
    """
    if entry is None or str(record.get("upos", "")).upper() != "NOUN":
        return entry
    if entry.pattern not in _SUPPORTED_PATTERNS:
        return entry

    lemma = _form_for_msd(entry, "ci") or entry.lemma
    singular_definite = _form_for_msd(entry, "sg def nom")
    plural_indefinite = _form_for_msd(entry, "pl indef nom")
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
