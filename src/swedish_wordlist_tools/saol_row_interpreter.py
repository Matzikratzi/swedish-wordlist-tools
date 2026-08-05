from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from .inflect import normalise_pattern
from .saol_notation import (
    FormOperation,
    FormOperationKind,
    apply_form_operation,
    assign_labeled_slots,
    parse_form_operation,
    split_alternative_branches,
)


@dataclass(frozen=True)
class KeyForm:
    slot: str
    written_form: str
    source: str


@dataclass(frozen=True)
class InterpretedRow:
    lemma: str
    pattern: str
    key_forms: tuple[KeyForm, ...]

    def form(self, slot: str) -> str | None:
        for key_form in self.key_forms:
            if key_form.slot == slot:
                return key_form.written_form
        return None


_SUP_ELEMENT_RE = re.compile(r"<sup\b[^>]*>.*?</sup>", re.IGNORECASE | re.DOTALL)
_HTML_TAG_RE = re.compile(r"<[^>]*>")
_NOUN_IGNORED_MARKERS = frozenset(
    {
        "i:",
        "anv:",
        "används:",
        "användas:",
        "kan:",
        "ofta:",
        "vanl:",
    }
)


def _comparison_key(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = _SUP_ELEMENT_RE.sub("", text)
    text = _HTML_TAG_RE.sub("", text)
    text = text.replace("\u00ad", "").replace("·", "")
    text = text.replace("‐", "-").replace("‑", "-").replace("–", "-")
    text = re.sub(r"\s+", " ", text).strip()
    return text.casefold()


def _clean_stycke(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = _SUP_ELEMENT_RE.sub("", text)
    text = _HTML_TAG_RE.sub("", text)
    return text.replace("\u00ad", "").replace("·", "").strip()


def _compound_parts(record: dict[str, Any], lemma: str) -> tuple[str, str] | None:
    stycke = _clean_stycke(record.get("stycke"))
    if "|" not in stycke:
        return None
    prefix, head = stycke.rsplit("|", 1)
    prefix = prefix.replace("|", "")
    if _comparison_key(prefix + head) != _comparison_key(lemma):
        return None
    return prefix, head


def _stycke_carrier(record: dict[str, Any], lemma: str) -> tuple[str, str] | None:
    """Return the phrase part identified by ``stycke`` and its trailing text.

    SAOL may store a phrase lemma such as ``företa sig`` while ``stycke``
    describes only the inflecting lexeme, for example ``före|ta``. In that
    case the carrier is ``företa`` and the untouched tail is `` sig``.
    """

    stycke = _clean_stycke(record.get("stycke"))
    if not stycke:
        return None
    carrier = stycke.replace("|", "")
    if not carrier:
        return None
    if _comparison_key(lemma) == _comparison_key(carrier):
        return carrier, ""
    if lemma.startswith(carrier + " "):
        return carrier, lemma[len(carrier) :]
    return None


def _common_prefix_length(left: str, right: str) -> int:
    length = 0
    for left_char, right_char in zip(left.casefold(), right.casefold()):
        if left_char != right_char:
            break
        length += 1
    return length


def _replace_unmarked_final_component(lemma: str, replacement: str) -> str | None:
    prefix, separator, final_word = lemma.rpartition(" ")
    target = final_word if separator else lemma
    best_start: int | None = None
    best_length = 0
    for start in range(len(target)):
        shared = _common_prefix_length(target[start:], replacement)
        if shared > best_length:
            best_start = start
            best_length = shared
    if best_start is None or best_length < 3:
        return None
    result = target[:best_start] + replacement
    return prefix + separator + result if separator else result


def _append_to_last_word(lemma: str, suffix: str) -> str:
    prefix, separator, final_word = lemma.rpartition(" ")
    if not separator:
        return lemma + suffix
    return prefix + separator + final_word + suffix


def _append_to_first_word(lemma: str, suffix: str) -> str:
    first, separator, rest = lemma.partition(" ")
    return first + suffix + (separator + rest if separator else "")


def _apply_to_carrier(
    record: dict[str, Any], carrier: str, operation: FormOperation
) -> str | None:
    if operation.kind is FormOperationKind.REPLACE_TAIL:
        parts = _compound_parts(record, carrier)
        if parts is not None:
            prefix, _head = parts
            return prefix + operation.value
    return apply_form_operation(
        carrier,
        operation,
        append=lambda value, suffix: value + suffix,
        replace_tail=_replace_unmarked_final_component,
    )


def apply_form_operation_to_noun(
    record: dict[str, Any], lemma: str, operation: FormOperation
) -> str | None:
    """Realize one already parsed operation for a noun lemma."""

    if operation.kind is FormOperationKind.REPLACE_TAIL:
        parts = _compound_parts(record, lemma)
        if parts is not None:
            prefix, _head = parts
            return prefix + operation.value

    return apply_form_operation(
        lemma,
        operation,
        append=_append_to_last_word,
        replace_tail=_replace_unmarked_final_component,
    )


def apply_form_token(
    record: dict[str, Any], lemma: str, token: str
) -> str | None:
    """Apply a raw form token to the lexeme selected by SAOL ``stycke``.

    For phrase lemmas, ``stycke`` is authoritative about the inflecting carrier:
    ``före|ta`` in ``företa sig`` yields ``företog sig``. When ``stycke`` does
    not identify a shorter carrier, the historical first-word fallback remains.
    """

    operation = parse_form_operation(token)
    if operation is None:
        return None

    carrier = _stycke_carrier(record, lemma)
    if carrier is not None:
        carrier_text, tail = carrier
        written_carrier = _apply_to_carrier(record, carrier_text, operation)
        if written_carrier is not None:
            return written_carrier + tail

    return apply_form_operation(
        lemma,
        operation,
        append=_append_to_first_word,
        replace_tail=_replace_unmarked_final_component,
    )


def _clean_notation_comments(pattern: str) -> str:
    pattern = _SUP_ELEMENT_RE.sub("", pattern)
    pattern = _HTML_TAG_RE.sub("", pattern)
    pattern = re.sub(
        r"(?:^|(?<=[;,]))\s*(?:som|i):\s*pl\.\s*(?:anv\.|används:)\s*(?:ofta:\s*|vanl\.\s*)?",
        " pl. ",
        pattern,
        flags=re.IGNORECASE,
    )
    pattern = re.sub(r"\b(?:ibl|vard|högt|vanl)\.\s*", "", pattern, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", pattern).strip()


def _interpret_missing_pattern(record: dict[str, Any], lemma: str) -> InterpretedRow | None:
    ordkl = re.sub(r"\s+", " ", str(record.get("ordkl", "")).strip()).casefold()
    key_forms: list[KeyForm] = [KeyForm("lemma", lemma, "lemma")]
    if "oböjl." in ordkl:
        return InterpretedRow(lemma, "(ordkl: oböjl.)", tuple(key_forms))
    if re.search(r"\bs\.\s*pl\.", ordkl):
        key_forms.append(KeyForm("pl_indef", lemma, "ordkl:s. pl."))
        return InterpretedRow(lemma, "(ordkl: pl.)", tuple(key_forms))
    if re.search(r"\bs\.\s*best\.", ordkl):
        key_forms.append(KeyForm("sg_def", lemma, "ordkl:s. best."))
        return InterpretedRow(lemma, "(ordkl: best.)", tuple(key_forms))
    return None


def interpret_noun_row(record: dict[str, Any]) -> InterpretedRow | None:
    if str(record.get("upos", "")).upper() != "NOUN":
        return None
    lemma = str(record.get("normaliserat_ord", "")).strip()
    pattern = normalise_pattern(record.get("text"))
    if not lemma:
        return None
    if pattern is None:
        return _interpret_missing_pattern(record, lemma)

    cleaned_pattern = _clean_notation_comments(pattern)
    branches = split_alternative_branches(cleaned_pattern)
    if not branches:
        return None

    key_forms: list[KeyForm] = [KeyForm("lemma", lemma, "lemma")]
    seen: set[tuple[str, str]] = {("lemma", lemma)}
    for branch in branches:
        slot_operations = assign_labeled_slots(
            branch.tokens,
            singular_slot="sg_def",
            plural_slot="pl_indef",
            definite_plural_slot="pl_def",
            ignored_markers=_NOUN_IGNORED_MARKERS,
        )
        if slot_operations is None:
            return None
        for assigned in slot_operations:
            written_form = apply_form_operation_to_noun(
                record, lemma, assigned.operation
            )
            if written_form is None:
                return None
            marker = (assigned.slot, written_form)
            if marker not in seen:
                seen.add(marker)
                key_forms.append(
                    KeyForm(assigned.slot, written_form, assigned.token)
                )

    return InterpretedRow(lemma, pattern, tuple(key_forms))
