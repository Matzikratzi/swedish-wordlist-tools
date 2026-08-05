from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from .inflect import normalise_pattern
from .saol_notation import (
    FormOperationKind,
    apply_form_operation,
    parse_form_operation,
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


_TOKEN_RE = re.compile(
    r"pl\.|best\.|el\.|[;,]|[+\-][A-Za-zÅÄÖåäöÉéÜü:]*|"
    r"[A-Za-zÅÄÖåäöÉéÜü0-9][\wÅÄÖåäöÉéÜü:‐‑–-]*",
    re.IGNORECASE,
)
_SUP_ELEMENT_RE = re.compile(r"<sup\b[^>]*>.*?</sup>", re.IGNORECASE | re.DOTALL)
_HTML_TAG_RE = re.compile(r"<[^>]*>")
_IGNORED_MARKERS = {
    "i:",
    "anv:",
    "används:",
    "användas:",
    "kan:",
    "ofta:",
    "vanl:",
}


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


def _common_prefix_length(left: str, right: str) -> int:
    length = 0
    for left_char, right_char in zip(left.casefold(), right.casefold()):
        if left_char != right_char:
            break
        length += 1
    return length


def _replace_unmarked_final_component(lemma: str, replacement: str) -> str | None:
    first, separator, rest = lemma.partition(" ")
    best_start: int | None = None
    best_length = 0
    for start in range(len(first)):
        shared = _common_prefix_length(first[start:], replacement)
        if shared > best_length:
            best_start = start
            best_length = shared
    if best_start is None or best_length < 3:
        return None
    result = first[:best_start] + replacement
    return result + (separator + rest if separator else "")


def _append_to_first_word(lemma: str, suffix: str) -> str:
    first, separator, rest = lemma.partition(" ")
    return first + suffix + (separator + rest if separator else "")


def apply_form_token(
    record: dict[str, Any], lemma: str, token: str
) -> str | None:
    """Apply one SAOL form instruction without deciding its grammatical slot."""

    operation = parse_form_operation(token)
    if operation is None:
        return None

    if operation.kind is FormOperationKind.REPLACE_TAIL:
        parts = _compound_parts(record, lemma)
        if parts is not None:
            prefix, _head = parts
            return prefix + operation.value

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


def _tokenize(pattern: str) -> tuple[str, ...] | None:
    tokens: list[str] = []
    position = 0
    for match in _TOKEN_RE.finditer(pattern):
        if pattern[position : match.start()].strip():
            return None
        tokens.append(match.group(0))
        position = match.end()
    if pattern[position:].strip():
        return None
    return tuple(tokens) if tokens else None


def _slot_sequence(pattern: str) -> tuple[tuple[str, str], ...] | None:
    tokens = _tokenize(_clean_notation_comments(pattern))
    if tokens is None:
        return None

    result: list[tuple[str, str]] = []
    context = "singular"
    pending_best = False
    seen_singular_form = False
    last_slot: str | None = None
    alternative_next = False
    saw_notation_marker = False

    for token in tokens:
        lower = token.casefold()
        if token in {";", ","}:
            saw_notation_marker = True
            continue
        if lower in _IGNORED_MARKERS:
            saw_notation_marker = True
            continue
        if lower in {"el.", "h"}:
            saw_notation_marker = True
            alternative_next = last_slot is not None
            continue
        if lower == "best.":
            saw_notation_marker = True
            pending_best = True
            alternative_next = False
            continue
        if lower == "pl.":
            saw_notation_marker = True
            context = "plural_definite" if pending_best else "plural"
            pending_best = False
            alternative_next = False
            continue

        operation = parse_form_operation(token)
        if operation is None:
            return None
        if operation.kind is not FormOperationKind.EXPLICIT:
            saw_notation_marker = True

        if alternative_next and last_slot is not None:
            slot = last_slot
            alternative_next = False
        elif context == "plural_definite":
            slot = "pl_def"
        elif context == "plural":
            slot = "pl_indef"
            context = "after_plural"
        elif not seen_singular_form:
            slot = "sg_def"
            seen_singular_form = True
        else:
            slot = "pl_indef"
            context = "after_plural"
        result.append((slot, token))
        last_slot = slot
        pending_best = False

    if not saw_notation_marker:
        return None
    return tuple(result) if result else None


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

    variants = tuple(
        part.strip() for part in re.split(r"\s+_\s+", pattern) if part.strip()
    )
    if not variants:
        return None

    key_forms: list[KeyForm] = [KeyForm("lemma", lemma, "lemma")]
    seen: set[tuple[str, str]] = {("lemma", lemma)}
    for variant in variants:
        slots = _slot_sequence(variant)
        if slots is None:
            return None
        for slot, token in slots:
            written_form = apply_form_token(record, lemma, token)
            if written_form is None:
                return None
            marker = (slot, written_form)
            if marker not in seen:
                seen.add(marker)
                key_forms.append(KeyForm(slot, written_form, token))

    return InterpretedRow(lemma, pattern, tuple(key_forms))
