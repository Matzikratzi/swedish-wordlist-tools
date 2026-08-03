from __future__ import annotations

import re
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

_ALTERNATIVE_GENDER_PATTERNS = {
    "+et el. +en",
    "+en el. +et",
    "+et el. +en; pl. +",
    "+en el. +et; pl. +",
}

_EXPLICIT_USED_PLURAL_RE = re.compile(
    r"^best\.\s*\+;\s*i:\s*pl\.\s*används:\s*(\S+)\s*$",
    re.IGNORECASE,
)

_OFFICER_PLURAL_RE = re.compile(
    r"^\+en;\s*som:\s*pl\.\s*anv\.\s*\+are,\s*best\.\s*pl\.\s*\+arna\s*$",
    re.IGNORECASE,
)

_SHORT_HEAD_PLURAL_RE = re.compile(
    r"^\+n\s+-(\S+)\s*$",
    re.IGNORECASE,
)


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


def _entry_from_alternative_gender_pattern(
    record: dict[str, Any], pattern: str
) -> GeneratedEntry | None:
    """Generate both singular genders from ``+et el. +en`` notation."""
    lemma = str(record.get("normaliserat_ord", "")).strip()
    if not lemma:
        return None
    definite_et = _attach_suffix(lemma, "et")
    definite_en = _attach_suffix(lemma, "en")
    return GeneratedEntry(
        lemma=lemma,
        pattern=pattern,
        word_forms=(
            GeneratedWordForm(lemma, _CI, "lemma"),
            GeneratedWordForm(_genitive(lemma), _SG_INDEF_GEN, "derived_genitive"),
            GeneratedWordForm(definite_et, _SG_DEF_NOM, "derived_alternative_gender"),
            GeneratedWordForm(_genitive(definite_et), _SG_DEF_GEN, "derived_genitive"),
            GeneratedWordForm(definite_en, _SG_DEF_NOM, "derived_alternative_gender"),
            GeneratedWordForm(_genitive(definite_en), _SG_DEF_GEN, "derived_genitive"),
        ),
        pattern_group=pattern,
    )


def _common_prefix_length(left: str, right: str) -> int:
    length = 0
    for left_char, right_char in zip(left.casefold(), right.casefold()):
        if left_char != right_char:
            break
        length += 1
    return length


def _bar_marked_compound_parts(record: dict[str, Any]) -> tuple[str, str] | None:
    """Return normalized compound prefix and head from SAOL ``stycke``.

    ``a·larm|knapp`` becomes ``("alarm", "knapp")``. The last bar is used,
    since a longer compound may contain more than one marked boundary.
    """
    stycke = str(record.get("stycke", "")).strip()
    if "|" not in stycke:
        return None
    prefix, head = stycke.rsplit("|", 1)
    prefix = prefix.replace("·", "").replace("|", "").strip()
    head = head.replace("·", "").strip()
    if not prefix or not head:
        return None
    return prefix, head


def _replace_bar_marked_head(
    record: dict[str, Any], replacement_head: str
) -> str | None:
    parts = _bar_marked_compound_parts(record)
    if parts is None:
        return None
    prefix, head = parts
    lemma = str(record.get("normaliserat_ord", "")).strip()
    if not lemma or lemma.casefold() != (prefix + head).casefold():
        return None
    return prefix + replacement_head


def _replace_compound_head(lemma: str, plural_head: str) -> str | None:
    """Fallback for records without a usable bar-marked ``stycke``."""
    best_start: int | None = None
    best_length = 0
    for start in range(len(lemma)):
        shared = _common_prefix_length(lemma[start:], plural_head)
        if shared > best_length:
            best_start = start
            best_length = shared
    if best_start is None or best_length < 3:
        return None
    return lemma[:best_start] + plural_head


def _explicit_used_plural(
    record: dict[str, Any], lemma: str, notation: str
) -> str | None:
    match = _EXPLICIT_USED_PLURAL_RE.fullmatch(notation.strip())
    if match is None:
        return None

    supplied = match.group(1)
    if not supplied.startswith("-"):
        return supplied
    plural_head = supplied[1:]
    return (
        _replace_bar_marked_head(record, plural_head)
        or _replace_compound_head(lemma, plural_head)
    )


def _entry_from_explicit_used_plural(
    record: dict[str, Any], notation: str
) -> GeneratedEntry | None:
    lemma = str(record.get("normaliserat_ord", "")).strip()
    if not lemma:
        return None
    plural = _explicit_used_plural(record, lemma, notation)
    if not plural:
        return None

    pattern = "best. +; i pl. används"
    return GeneratedEntry(
        lemma=lemma,
        pattern=pattern,
        word_forms=(
            GeneratedWordForm(lemma, _CI, "lemma"),
            GeneratedWordForm(lemma, _SG_DEF_NOM, "derived"),
            GeneratedWordForm(plural, _PL_INDEF_NOM, "explicit_plural"),
        ),
        pattern_group=pattern,
    )


def _entry_from_short_head_plural(
    record: dict[str, Any], notation: str
) -> GeneratedEntry | None:
    """Parse short SAOL notation such as ``+n -knappar``.

    The compound head is taken from ``stycke`` rather than guessed from the
    lemma. For ``a·larm|klocka`` this yields ``alarmklockor``.
    """
    match = _SHORT_HEAD_PLURAL_RE.fullmatch(notation.strip())
    if match is None:
        return None
    lemma = str(record.get("normaliserat_ord", "")).strip()
    if not lemma:
        return None
    plural = _replace_bar_marked_head(record, match.group(1))
    if not plural:
        return None
    pattern = "+n explicit compound-head plural"
    return GeneratedEntry(
        lemma=lemma,
        pattern=pattern,
        word_forms=(
            GeneratedWordForm(lemma, _CI, "lemma"),
            GeneratedWordForm(lemma + "n", _SG_DEF_NOM, "derived"),
            GeneratedWordForm(plural, _PL_INDEF_NOM, "explicit_plural"),
        ),
        pattern_group=pattern,
    )


def _entry_from_officer_plural_comment(
    record: dict[str, Any], notation: str
) -> GeneratedEntry | None:
    if _OFFICER_PLURAL_RE.fullmatch(notation.strip()) is None:
        return None
    lemma = str(record.get("normaliserat_ord", "")).strip()
    if not lemma:
        return None
    singular_definite = lemma + "en"
    plural_indefinite = lemma + "are"
    plural_definite = lemma + "arna"
    pattern = "+en; som pl. används +are"
    return GeneratedEntry(
        lemma=lemma,
        pattern=pattern,
        word_forms=(
            GeneratedWordForm(lemma, _CI, "lemma"),
            GeneratedWordForm(_genitive(lemma), _SG_INDEF_GEN, "derived_genitive"),
            GeneratedWordForm(singular_definite, _SG_DEF_NOM, "derived"),
            GeneratedWordForm(_genitive(singular_definite), _SG_DEF_GEN, "derived_genitive"),
            GeneratedWordForm(plural_indefinite, _PL_INDEF_NOM, "explicit_plural"),
            GeneratedWordForm(_genitive(plural_indefinite), _PL_INDEF_GEN, "derived_genitive"),
            GeneratedWordForm(plural_definite, _PL_DEF_NOM, "explicit_definite_plural"),
            GeneratedWordForm(_genitive(plural_definite), _PL_DEF_GEN, "derived_genitive"),
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
    if pattern == "best. +; i pl. används":
        return plural + ("a" if plural.casefold().endswith("en") else "na")
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

    raw_pattern = str(record.get("text", "")).strip()
    explicit_plural_entry = _entry_from_explicit_used_plural(record, raw_pattern)
    if explicit_plural_entry is not None:
        return _complete_full_paradigm(explicit_plural_entry)

    if _SHORT_HEAD_PLURAL_RE.fullmatch(raw_pattern) is not None:
        short_head_plural_entry = _entry_from_short_head_plural(record, raw_pattern)
        if short_head_plural_entry is None:
            return None
        return _complete_full_paradigm(short_head_plural_entry)

    officer_entry = _entry_from_officer_plural_comment(record, raw_pattern)
    if officer_entry is not None:
        return officer_entry

    pattern = normalise_pattern(raw_pattern)
    if pattern is None:
        pattern = raw_pattern

    if pattern in _ALTERNATIVE_GENDER_PATTERNS:
        return _entry_from_alternative_gender_pattern(record, pattern)

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
