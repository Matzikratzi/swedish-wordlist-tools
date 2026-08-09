from __future__ import annotations

import re
from dataclasses import replace
from typing import Any

from .inflect import GeneratedEntry, GeneratedWordForm
from .msd import parse_msd
from .noun_source_errors import noun_lemma_only_source_error
from .saol_notation import FormOperationKind, parse_form_operation
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

_EXPLICIT_PLURAL_USE_RE = re.compile(
    r"\bpl\.\s*(?:anv\.|används:)\s*",
    re.IGNORECASE,
)


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


def _lemma_only_entry(record: dict[str, Any], reason: str) -> GeneratedEntry | None:
    """Preserve only the headword when source data makes forms unreliable."""

    lemma = str(record.get("normaliserat_ord", "")).strip()
    if not lemma:
        return None
    return GeneratedEntry(
        lemma=lemma,
        pattern=f"(source error: {reason})",
        word_forms=(GeneratedWordForm(lemma, _CI, "lemma"),),
        pattern_group="source-error lemma only",
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
) -> str | None:
    """Derive a definite plural only where the morphology is mechanically licensed.

    Reference: Svenska Akademiens grammatik (SAG), vol. 2, Substantiv §68,
    especially pp. 101–103 in the printed pagination (PDF pp. 104–107), together
    with §51 for the sixth declension.

    Relevant rules used here:

    * ordinary plural suffixes ending in ``-r`` take definite ``-na``;
    * fifth-declension plural ``-n`` takes definite ``-a``;
    * sixth-declension zero plural normally takes ``-en`` in the cases relevant
      here, including the stem-changing plurals ``gäss, löss, möss, män``;
    * Latin/Greek plurals in ``-a`` and ``-i`` take no definiteness suffix;
    * ``-s`` plural does *not* have one safe general definite-plural rule. SAG
      licenses ``-en`` for one-syllable stems and describes avoidance/variation
      elsewhere.  Since SAOL's compact notation does not encode syllable count
      or a definite form here, we do not invent one unless SAOL supplied the
      definite-plural slot explicitly.

    This function therefore returns ``None`` where SAG does not give us enough
    information to derive a unique form mechanically from the article data.
    """
    folded_plural = plural.casefold()
    folded_lemma = lemma.casefold()
    folded_singulars = tuple(form.casefold() for form in singular_definites)
    neuter = any(form.endswith("t") for form in folded_singulars)

    # Sixth declension, zero plural.  For ordinary neuters this is e.g.
    # hus -> husen.  Lemmas ending in e take only -n: apanage -> apanagen.
    if folded_plural == folded_lemma:
        if neuter:
            return lemma + ("n" if folded_lemma.endswith("e") else "en")
        # Utrum zero-plural has several subtypes in SAG §68:3.  Derive only the
        # very robust irregular-stem cases elsewhere below; otherwise require
        # an explicit SAOL definite-plural slot.
        return None

    # First–fourth declension productive plural endings all end in -r and take
    # -na in definite plural: hundar -> hundarna, idéer -> idéerna, skor -> skorna.
    if folded_plural.endswith("r"):
        return plural + "na"

    # Fifth declension -n takes -a: alibin -> alibina, hjärtan -> hjärtana.
    # Here neuter singular definiteness is our mechanical signal that an explicit
    # plural in -n belongs to this pattern rather than to a sixth-declension stem.
    if folded_plural.endswith("n") and neuter:
        return plural + "a"

    # Latin/Greek plural forms in -a/-i are used unchanged where definite plural
    # would otherwise be expected (SAG §68:5): tentamina, fora etc.
    if folded_plural.endswith(("a", "i")):
        return plural

    # Stem-changing sixth-declension plurals (SAG §51, §68:3c) have no plural
    # suffix even though the plural stem differs from the singular: gäss, löss,
    # möss, män.  They take -en in definite plural.
    if folded_plural.endswith(("gäss", "löss", "möss", "män")):
        return plural + "en"

    # A generic written -s plural is deliberately *not* completed here.  SAG
    # §68:4 gives -en for one-syllable stems but variation/avoidance elsewhere;
    # deriving from orthographic final -s alone would overgenerate.
    if folded_plural.endswith("s"):
        return None

    return None


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
    if not plural_definites and singular_definites:
        # Derive only where SAG gives a unique mechanical form.  If it does not,
        # keep the SAOL-licensed indefinite plural but leave the definite slot
        # absent rather than guessing.
        for plural in plural_indefinites:
            derived = _derive_definite_plural(lemma, singular_definites, plural)
            if derived is not None:
                plural_definites.append(derived)

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


def _has_unmarked_replacement(row: InterpretedRow) -> bool:
    return any(
        operation is not None and operation.kind is FormOperationKind.REPLACE_TAIL
        for form in row.key_forms
        if form.slot != "lemma"
        for operation in (parse_form_operation(form.source),)
    )


def _replacement_is_explicit_plural_use(record: dict[str, Any]) -> bool:
    """Return whether prose explicitly licenses a supplied plural replacement."""
    return _EXPLICIT_PLURAL_USE_RE.search(str(record.get("text", ""))) is not None


def _has_usable_compound_bar(record: dict[str, Any], lemma: str) -> bool:
    stycke = str(record.get("stycke", ""))
    if "|" not in stycke:
        return False
    normalized = stycke.replace("·", "").replace("|", "").strip()
    return normalized.casefold() == lemma.casefold()


def complete_noun_entry(
    record: dict[str, Any],
    entry: GeneratedEntry | None,
) -> GeneratedEntry | None:
    """Build a noun paradigm from SAOL operations mapped to noun slots."""
    if str(record.get("upos", "")).upper() != "NOUN":
        return entry

    source_error = noun_lemma_only_source_error(record)
    if source_error is not None:
        return _lemma_only_entry(record, source_error)

    row = interpret_noun_row(record)
    if row is None:
        return None

    if (
        _has_unmarked_replacement(row)
        and not _has_usable_compound_bar(record, row.lemma)
        and not _replacement_is_explicit_plural_use(record)
    ):
        return None

    interpreted = _entry_from_interpreted_row(row)
    return _complete_from_slots(interpreted)
