from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from .saol_notation import (
    FormOperation,
    FormOperationKind,
    apply_form_operation,
    assign_labeled_slots,
    parse_form_operation,
    parse_form_operations,
    split_alternative_branches,
)
from .saol_slot_interpreter import SlotGrammar, assign_slots_with_grammar
from .saol_source_policy import inflection_text


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
_LEADING_HOMONYM_RE = re.compile(r"^\d+(?=\D)")


def _comparison_key(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = _SUP_ELEMENT_RE.sub("", text)
    text = _HTML_TAG_RE.sub("", text)
    text = text.replace("\u00ad", "").replace("·", "")
    text = text.replace("‐", "-").replace("‑", "-").replace("–", "-")
    text = re.sub(r"\s+", " ", text).strip()
    return _LEADING_HOMONYM_RE.sub("", text).casefold()


def _clean_surface(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = _SUP_ELEMENT_RE.sub("", text)
    text = _HTML_TAG_RE.sub("", text)
    text = text.replace("\u00ad", "").replace("·", "").strip()
    return _LEADING_HOMONYM_RE.sub("", text)


def _join_compound_boundary(prefix: str, head: str) -> str:
    """Join SAOL compound parts using ordinary Swedish triple-consonant spelling."""

    if (
        len(prefix) >= 2
        and head
        and prefix[-1].casefold() == prefix[-2].casefold() == head[0].casefold()
    ):
        return prefix[:-1] + head
    return prefix + head


def _structural_surfaces(record: dict[str, Any]) -> tuple[str, ...]:
    values: list[str] = []
    for field in ("stycke", "ord"):
        cleaned = _clean_surface(record.get(field))
        if cleaned and cleaned not in values:
            values.append(cleaned)
    return tuple(values)


def compound_parts(record: dict[str, Any], lemma: str) -> tuple[str, str] | None:
    """Return a structurally verified prefix/head split for the normalized lemma."""

    for surface in _structural_surfaces(record):
        if "|" not in surface:
            continue
        prefix, head = surface.rsplit("|", 1)
        prefix = prefix.replace("|", "")
        literal = prefix + head
        normalized = _join_compound_boundary(prefix, head)
        if (
            _comparison_key(literal) == _comparison_key(lemma)
            or _comparison_key(normalized) == _comparison_key(lemma)
        ):
            return prefix, head
    return None


def _stycke_carrier(record: dict[str, Any], lemma: str) -> tuple[str, str] | None:
    stycke = _clean_surface(record.get("stycke"))
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


def _append_to_hyphen_component(word: str, suffix: str) -> str:
    prefix, separator, component = word.rpartition("-")
    if (
        separator
        and component
        and len(suffix) > len(component)
        and suffix.casefold().startswith(component.casefold())
    ):
        return prefix + separator + suffix
    return word + suffix


def _append_to_last_word(lemma: str, suffix: str) -> str:
    prefix, separator, final_word = lemma.rpartition(" ")
    result = _append_to_hyphen_component(final_word if separator else lemma, suffix)
    return prefix + separator + result if separator else result


def _append_to_first_word(lemma: str, suffix: str) -> str:
    first, separator, rest = lemma.partition(" ")
    result = _append_to_hyphen_component(first, suffix)
    return result + (separator + rest if separator else "")


def _apply_to_carrier(record: dict[str, Any], carrier: str, operation: FormOperation) -> str | None:
    if operation.kind is FormOperationKind.REPLACE_TAIL:
        parts = compound_parts(record, carrier)
        if parts is not None:
            prefix, _head = parts
            return _join_compound_boundary(prefix, operation.value)
    return apply_form_operation(
        carrier,
        operation,
        append=_append_to_last_word,
        replace_tail=_replace_unmarked_final_component,
    )


def apply_form_operation_to_noun(record: dict[str, Any], lemma: str, operation: FormOperation) -> str | None:
    if operation.kind is FormOperationKind.REPLACE_TAIL:
        parts = compound_parts(record, lemma)
        if parts is not None:
            prefix, _head = parts
            return _join_compound_boundary(prefix, operation.value)

    return apply_form_operation(
        lemma,
        operation,
        append=_append_to_last_word,
        replace_tail=_replace_unmarked_final_component,
    )


def apply_form_token(record: dict[str, Any], lemma: str, token: str) -> str | None:
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


def _clean_notation_structure(pattern: str) -> str:
    pattern = _SUP_ELEMENT_RE.sub("", pattern)
    pattern = _HTML_TAG_RE.sub("", pattern)
    return re.sub(r"\s+", " ", pattern).strip()


def _interpret_missing_pattern(record: dict[str, Any], lemma: str) -> InterpretedRow | None:
    ordkl = re.sub(r"\s+", " ", str(record.get("ordkl", "")).strip()).casefold()
    key_forms: list[KeyForm] = [KeyForm("lemma", lemma, "lemma")]
    if "oböjl." in ordkl:
        return InterpretedRow(lemma, "(ordkl: oböjl.)", tuple(key_forms))
    if re.search(r"\bs\.\s*pl\.", ordkl):
        key_forms.append(KeyForm("pl_indef", lemma, "ordkl:s. pl."))
        return InterpretedRow(lemma, "(ordkl: pl.)", tuple(key_forms))
    if re.search(r"(?:\bs\.\s*)?\bbest\.(?!\s*pl\.)", ordkl):
        key_forms.append(KeyForm("sg_def", lemma, "ordkl:best."))
        return InterpretedRow(lemma, "(ordkl: best.)", tuple(key_forms))
    return None


def _colon_stem(value: str) -> str | None:
    stem, separator, _ending = value.partition(":")
    return stem if separator and stem else None


def _branch_lemma_variant(lemma: str, tokens: tuple[str, ...]) -> tuple[str, str] | None:
    for token in tokens:
        operations = parse_form_operations(token)
        if operations is None:
            continue
        for operation in operations:
            stem = _colon_stem(operation.value)
            if stem is None:
                continue
            if operation.kind is FormOperationKind.EXPLICIT:
                if stem.casefold() == lemma.casefold() and stem != lemma:
                    return stem, token
                continue
            if operation.kind is not FormOperationKind.APPEND:
                continue
            prefix, separator, component = lemma.rpartition("-")
            if separator and stem.casefold() == component.casefold() and stem != component:
                return prefix + separator + stem, token
            if stem.casefold() == lemma.casefold() and stem != lemma:
                return stem, token
        return None
    return None


def _explicit_branch_bases(record: dict[str, Any], lemma: str, branch_count: int) -> tuple[str, ...]:
    alternative = str(record.get("_saol_alternative_lemma") or "").strip()
    if branch_count == 2 and alternative and alternative.casefold() != lemma.casefold():
        return (lemma, alternative)
    return tuple(lemma for _ in range(branch_count))


def _noun_shared_implicit_slot(index: int, last_slot: str | None, _operation: FormOperation) -> str | None:
    """Map successive unlabelled noun operations to their ordinary slots."""

    if index == 0:
        return "sg_def"
    if last_slot in {"pl_indef", "pl_def"}:
        return last_slot
    return "pl_indef"


_NOUN_ALTERNATIVE_MARKERS = frozenset({"el.", "h", "ibl."})
_NOUN_TRANSPARENT_MARKERS = frozenset({"vard."})

_NOUN_LABELLED_SLOT_GRAMMAR = SlotGrammar(
    label_slots={
        "pl.": "pl_indef",
        "best.": "sg_def",
        "best.pl.": "pl_def",
    },
    implicit_slot=_noun_shared_implicit_slot,
    alternative_markers=_NOUN_ALTERNATIVE_MARKERS,
    transparent_markers=_NOUN_TRANSPARENT_MARKERS,
    require_marker=True,
)

_NOUN_UNLABELLED_SLOT_GRAMMAR = SlotGrammar(
    label_slots={},
    implicit_slot=_noun_shared_implicit_slot,
    alternative_markers=_NOUN_ALTERNATIVE_MARKERS,
    transparent_markers=_NOUN_TRANSPARENT_MARKERS,
    require_marker=False,
)


def _coalesce_noun_slot_labels(tokens: tuple[str, ...]) -> tuple[str, ...]:
    """Treat ``best. pl.`` as one noun slot label before generic assignment."""

    result: list[str] = []
    index = 0
    while index < len(tokens):
        if (
            tokens[index].casefold() == "best."
            and index + 1 < len(tokens)
            and tokens[index + 1].casefold() == "pl."
        ):
            result.append("best.pl.")
            index += 2
            continue
        result.append(tokens[index])
        index += 1
    return tuple(result)


def _has_noun_slot_label(tokens: tuple[str, ...]) -> bool:
    lowered = tuple(token.casefold() for token in tokens)
    return "pl." in lowered or "best." in lowered


def _is_noun_alternative_marker(token: str) -> bool:
    return token.strip().strip("()").casefold() in _NOUN_ALTERNATIVE_MARKERS


def _is_noun_transparent_marker(token: str) -> bool:
    return token.strip().strip("()").casefold() in _NOUN_TRANSPARENT_MARKERS


def _assign_labelled_noun_slots_shared(tokens: tuple[str, ...]):
    """Use the shared engine only for branches with explicit noun slot labels."""

    if not _has_noun_slot_label(tokens):
        return None
    return assign_slots_with_grammar(
        _coalesce_noun_slot_labels(tokens),
        _NOUN_LABELLED_SLOT_GRAMMAR,
    )


def _assign_unlabelled_relative_noun_slots_shared(tokens: tuple[str, ...]):
    """Compose relative atoms and same-slot alternatives without a paradigm rule."""

    saw_form = False
    for token in tokens:
        if (
            token in {",", ";"}
            or _is_noun_alternative_marker(token)
            or _is_noun_transparent_marker(token)
        ):
            continue
        operations = parse_form_operations(token)
        if operations is None:
            return None
        if any(operation.kind is FormOperationKind.EXPLICIT for operation in operations):
            return None
        saw_form = True
    if not saw_form:
        return None
    return assign_slots_with_grammar(tokens, _NOUN_UNLABELLED_SLOT_GRAMMAR)


def _assign_unlabelled_explicit_noun_slots_shared(
    record: dict[str, Any],
    tokens: tuple[str, ...],
):
    """Assign explicit full forms and same-slot alternatives in noun context."""

    ordkl = re.sub(r"\s+", " ", str(record.get("ordkl", "")).strip()).casefold()
    if re.search(r"\bs\.", ordkl) is None:
        return None

    saw_form = False
    for token in tokens:
        if (
            token in {",", ";"}
            or _is_noun_alternative_marker(token)
            or _is_noun_transparent_marker(token)
        ):
            continue
        operations = parse_form_operations(token)
        if operations is None:
            return None
        if any(operation.kind is not FormOperationKind.EXPLICIT for operation in operations):
            return None
        saw_form = True
    if not saw_form:
        return None
    return assign_slots_with_grammar(tokens, _NOUN_UNLABELLED_SLOT_GRAMMAR)


def _assign_noun_slots(record: dict[str, Any], tokens: tuple[str, ...]):
    """Assign noun notation through shared atoms, with the established fallback."""

    shared = _assign_labelled_noun_slots_shared(tokens)
    if shared is not None:
        return shared

    shared = _assign_unlabelled_relative_noun_slots_shared(tokens)
    if shared is not None:
        return shared

    shared = _assign_unlabelled_explicit_noun_slots_shared(record, tokens)
    if shared is not None:
        return shared

    return assign_labeled_slots(
        tokens,
        singular_slot="sg_def",
        plural_slot="pl_indef",
        definite_plural_slot="pl_def",
    )


def _is_uninflected_branch(tokens: tuple[str, ...]) -> bool:
    """Return true for a branch whose base form is explicitly uninflected."""

    meaningful = tuple(
        token.casefold()
        for token in tokens
        if token not in {";", ","}
    )
    return meaningful == ("oböjl.",)


def interpret_noun_row(record: dict[str, Any]) -> InterpretedRow | None:
    if str(record.get("upos", "")).upper() != "NOUN":
        return None
    lemma = str(record.get("normaliserat_ord", "")).strip()
    pattern = inflection_text(record)
    if not lemma:
        return None
    if pattern is None:
        return _interpret_missing_pattern(record, lemma)

    cleaned_pattern = _clean_notation_structure(pattern)
    branches = split_alternative_branches(cleaned_pattern)
    if not branches:
        return None

    branch_bases = _explicit_branch_bases(record, lemma, len(branches))
    key_forms: list[KeyForm] = [KeyForm("lemma", lemma, "lemma")]
    seen: set[tuple[str, str]] = {("lemma", lemma)}
    for branch_index, branch in enumerate(branches):
        branch_base = branch_bases[branch_index]
        if branch_base.casefold() != lemma.casefold():
            marker = ("lemma", branch_base)
            if marker not in seen:
                seen.add(marker)
                key_forms.append(KeyForm("lemma", branch_base, "explicit_variant_branch"))

        if _is_uninflected_branch(branch.tokens):
            continue

        lemma_variant = _branch_lemma_variant(branch_base, branch.tokens)
        if lemma_variant is not None:
            written_form, source = lemma_variant
            marker = ("lemma", written_form)
            if marker not in seen:
                seen.add(marker)
                key_forms.append(KeyForm("lemma", written_form, source))

        slot_operations = _assign_noun_slots(record, branch.tokens)
        if slot_operations is None:
            return None
        for assigned in slot_operations:
            written_form = apply_form_operation_to_noun(record, branch_base, assigned.operation)
            if written_form is None:
                return None
            marker = (assigned.slot, written_form)
            if marker not in seen:
                seen.add(marker)
                key_forms.append(KeyForm(assigned.slot, written_form, assigned.token))

    return InterpretedRow(lemma, pattern, tuple(key_forms))