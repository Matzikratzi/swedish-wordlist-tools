from __future__ import annotations

from dataclasses import replace
from typing import Any

from .inflect import GeneratedEntry, GeneratedWordForm
from .msd import parse_msd
from .saol_row_interpreter import InterpretedRow, interpret_noun_row

_CI = parse_msd("ci")
_SG_INDEF_GEN = parse_msd("sg indef gen")
_SG_DEF_NOM = parse_msd("sg def nom")
_SG_DEF_GEN = parse_msd("sg def gen")
_PL_INDEF_NOM = parse_msd("pl indef nom")
_PL_INDEF_GEN = parse_msd("pl indef gen")
_PL_DEF_NOM = parse_msd("pl def nom")
_PL_DEF_GEN = parse_msd("pl def gen")

_SLOT_MSD = {
    "lemma": _CI,
    "sg_def": _SG_DEF_NOM,
    "pl_indef": _PL_INDEF_NOM,
    "pl_def": _PL_DEF_NOM,
}


def _genitive(form: str) -> str:
    """Return the ordinary Swedish genitive spelling."""
    return form if form.casefold().endswith(("s", "x", "z")) else form + "s"


def _entry_from_interpreted_row(row: InterpretedRow) -> GeneratedEntry:
    """Convert interpreted noun slots to the legacy generated-entry shape."""
    forms: list[GeneratedWordForm] = []
    seen: set[tuple[str, str]] = set()
    for key_form in row.key_forms:
        msd = _SLOT_MSD.get(key_form.slot)
        if msd is None:
            continue
        marker = (key_form.written_form, str(msd))
        if marker in seen:
            continue
        seen.add(marker)
        kind = "lemma" if key_form.slot == "lemma" else "interpreted_slot"
        forms.append(GeneratedWordForm(key_form.written_form, msd, kind))
    return GeneratedEntry(
        lemma=row.lemma,
        pattern=row.pattern,
        word_forms=tuple(forms),
        pattern_group="interpreted noun slots",
    )


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


def _forms_for_msd(entry: GeneratedEntry, wanted: str) -> tuple[str, ...]:
    wanted_msd = parse_msd(wanted).casefold()
    return tuple(
        form.written_form
        for form in entry.word_forms
        if form.msd is not None and form.msd.casefold() == wanted_msd
    )


def _derive_definite_plural(
    lemma: str,
    singular_definites: tuple[str, ...],
    plural: str,
) -> str:
    """Derive the regular definite plural from interpreted key forms.

    The decision uses the forms SAOL supplied, not the spelling of the complete
    notation pattern:

    * zero plural with an ``-et`` singular takes ``-en``;
    * an ``-n`` plural paired with an ``-t`` singular takes ``-a``;
    * other plurals take regular ``-na``;
    * plurals already ending in ``-en`` take ``-a``.
    """
    folded_plural = plural.casefold()
    folded_lemma = lemma.casefold()
    folded_singulars = tuple(form.casefold() for form in singular_definites)

    if folded_plural == folded_lemma and any(form.endswith("et") for form in folded_singulars):
        return lemma + "en"
    if folded_plural.endswith("n") and any(form.endswith("t") for form in folded_singulars):
        return plural + "a"
    if folded_plural.endswith("en"):
        return plural + "a"
    return plural + "na"


def _complete_from_slots(entry: GeneratedEntry) -> GeneratedEntry:
    lemma = (_forms_for_msd(entry, "ci") or (entry.lemma,))[0]
    singular_definites = _forms_for_msd(entry, "sg def nom")
    plural_indefinites = _forms_for_msd(entry, "pl indef nom")
    explicit_plural_definites = _forms_for_msd(entry, "pl def nom")

    additions: list[GeneratedWordForm] = [
        GeneratedWordForm(lemma, _CI, "lemma"),
        GeneratedWordForm(_genitive(lemma), _SG_INDEF_GEN, "derived_genitive"),
    ]

    for singular in singular_definites:
        additions.extend(
            (
                GeneratedWordForm(singular, _SG_DEF_NOM, "interpreted_slot"),
                GeneratedWordForm(_genitive(singular), _SG_DEF_GEN, "derived_genitive"),
            )
        )

    for plural in plural_indefinites:
        additions.extend(
            (
                GeneratedWordForm(plural, _PL_INDEF_NOM, "interpreted_slot"),
                GeneratedWordForm(_genitive(plural), _PL_INDEF_GEN, "derived_genitive"),
            )
        )

    plural_definites = list(explicit_plural_definites)
    if not plural_definites:
        plural_definites.extend(
            _derive_definite_plural(lemma, singular_definites, plural)
            for plural in plural_indefinites
        )

    for plural_definite in plural_definites:
        additions.extend(
            (
                GeneratedWordForm(plural_definite, _PL_DEF_NOM, "derived_definite_plural"),
                GeneratedWordForm(
                    _genitive(plural_definite),
                    _PL_DEF_GEN,
                    "derived_genitive",
                ),
            )
        )

    return _merge_forms(entry, tuple(additions))


def complete_noun_entry(
    record: dict[str, Any],
    entry: GeneratedEntry | None,
) -> GeneratedEntry | None:
    """Build a noun paradigm from SAOL operations mapped to noun slots.

    ``entry`` is retained in the signature for callers that still run the old
    base generator first, but noun completion no longer depends on its pattern
    classes. The interpreted SAOL row is authoritative.
    """
    if str(record.get("upos", "")).upper() != "NOUN":
        return entry

    row = interpret_noun_row(record)
    if row is None:
        return None

    interpreted = _entry_from_interpreted_row(row)
    return _complete_from_slots(interpreted)
