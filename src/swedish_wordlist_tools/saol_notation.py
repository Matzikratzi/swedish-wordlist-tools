from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Callable


@dataclass(frozen=True)
class NotationBranch:
    """One SAOL alternative branch with validated notation tokens."""

    text: str
    tokens: tuple[str, ...]


class FormOperationKind(str, Enum):
    """Primitive operations used by SAOL inflection notation."""

    UNCHANGED = "unchanged"
    APPEND = "append"
    REPLACE_TAIL = "replace_tail"
    EXPLICIT = "explicit"


@dataclass(frozen=True)
class FormOperation:
    """An ordklass-neutral interpretation of one form token."""

    kind: FormOperationKind
    value: str = ""
    source: str = ""


@dataclass(frozen=True)
class SlotOperation:
    """One form operation assigned to an ordklass-provided grammatical slot."""

    slot: str
    token: str
    operation: FormOperation


_BRACKET_COMMENT = re.compile(r"\s*\[[^\]]*\]")
_HTML_TAG = re.compile(r"</?[^>]+>")
_GLUED_LABEL_OPERATION = re.compile(
    r"(?<!\w)([A-Za-zÅÄÖåäöÉéÜü]+\.)(?=[+\-])"
)
_TRUNCATED_FINAL_TOKEN = re.compile(r"(?:^|\s)\S+-$")
_FORM_PAYLOAD = re.compile(r"[^\s;,_]+")
_EXPLICIT_FORM = re.compile(r"[^\s;,+_]+")
_OPTIONAL_OPERATION = re.compile(r"^([+\-])([^()]*)\(([^()]+)\)([^()]*)$")
_NOTATION_TOKEN_RE = re.compile(
    r"pl\.|best\.|el\.|[;,]|[+\-][^\s;,_]*|[^\s;,+_]+",
    re.IGNORECASE,
)
_SOURCE_TEXT_LIMIT = 50


def _drop_truncated_final_token(text: str) -> str:
    """Drop a visibly cut-off final token at SAOL export's text limit."""

    if len(text) != _SOURCE_TEXT_LIMIT or not _TRUNCATED_FINAL_TOKEN.search(text):
        return text
    return _TRUNCATED_FINAL_TOKEN.sub("", text).rstrip()


def _clean_notation_spelling(text: str) -> str:
    text = _drop_truncated_final_token(text)
    without_tags = _HTML_TAG.sub("", text)
    without_brackets = _BRACKET_COMMENT.sub("", without_tags)
    with_label_boundaries = _GLUED_LABEL_OPERATION.sub(r"\1 ", without_brackets)
    return " ".join(with_label_boundaries.split())


def _unwrap_token(token: str) -> str:
    return _HTML_TAG.sub("", token.strip()).strip("()")


def _is_comment_word(token: str) -> bool:
    raw = _unwrap_token(token)
    return bool(raw) and not raw.startswith(("+", "-")) and raw.endswith(":")


def _is_generic_label(token: str) -> bool:
    raw = _unwrap_token(token)
    return bool(raw) and not raw.startswith(("+", "-")) and raw.endswith(".")


def normalize_notation(text: str) -> str:
    return _clean_notation_spelling(text).casefold()


def tokenize_notation(text: str) -> tuple[str, ...] | None:
    """Tokenize one SAOL notation branch without changing form spelling."""

    cleaned = _clean_notation_spelling(text)
    tokens: list[str] = []
    position = 0
    for match in _NOTATION_TOKEN_RE.finditer(cleaned):
        if cleaned[position : match.start()].strip():
            return None
        tokens.append(match.group(0))
        position = match.end()
    if cleaned[position:].strip():
        return None
    return tuple(tokens) if tokens else None


def parse_form_operation(token: str) -> FormOperation | None:
    raw = _unwrap_token(token)
    normalized = raw.casefold()
    if normalized == "+":
        return FormOperation(FormOperationKind.UNCHANGED, source=raw)
    if normalized.startswith("+-"):
        value = raw[2:]
        if value and _FORM_PAYLOAD.fullmatch(value):
            return FormOperation(FormOperationKind.APPEND, value, raw)
        return None
    if normalized.startswith("+"):
        value = raw[1:]
        if value and _FORM_PAYLOAD.fullmatch(value):
            return FormOperation(FormOperationKind.APPEND, value, raw)
        return None
    if normalized.startswith("-"):
        value = raw[1:]
        if value and _FORM_PAYLOAD.fullmatch(value):
            return FormOperation(FormOperationKind.REPLACE_TAIL, value, raw)
        return None

    if (
        not raw
        or _is_comment_word(raw)
        or _is_generic_label(raw)
        or not raw[0].isalnum()
        or not _EXPLICIT_FORM.fullmatch(raw)
    ):
        return None
    return FormOperation(FormOperationKind.EXPLICIT, raw, raw)


def parse_form_operations(token: str) -> tuple[FormOperation, ...] | None:
    """Parse a token and expand one parenthesized optional payload segment.

    For example, ``+(e)n`` expands mechanically to ``+n`` and ``+en``.
    No word, suffix, or part of speech is encoded in this rule.
    """

    raw = _unwrap_token(token)
    match = _OPTIONAL_OPERATION.fullmatch(raw)
    if match is None:
        operation = parse_form_operation(raw)
        return (operation,) if operation is not None else None

    marker, before, optional, after = match.groups()
    variants = (marker + before + after, marker + before + optional + after)
    operations: list[FormOperation] = []
    for variant in variants:
        operation = parse_form_operation(variant)
        if operation is None:
            return None
        if operation not in operations:
            operations.append(operation)
    return tuple(operations)


def assign_labeled_slots(
    tokens: tuple[str, ...],
    *,
    singular_slot: str,
    plural_slot: str,
    definite_plural_slot: str,
    ignored_markers: frozenset[str] = frozenset(),
) -> tuple[SlotOperation, ...] | None:
    """Assign form operations while ignoring SAOL's explanatory prose."""

    result: list[SlotOperation] = []
    context = "singular"
    pending_best = False
    seen_singular_form = False
    last_slot: str | None = None
    alternative_next = False
    saw_notation_marker = False

    for token in tokens:
        raw = _unwrap_token(token)
        lower = raw.casefold()
        if raw in {";", ","}:
            saw_notation_marker = True
            continue
        if lower in ignored_markers:
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
        if _is_comment_word(raw) or _is_generic_label(raw):
            saw_notation_marker = True
            continue

        operations = parse_form_operations(raw)
        if operations is None:
            return None
        if any(operation.kind is not FormOperationKind.EXPLICIT for operation in operations):
            saw_notation_marker = True

        if alternative_next and last_slot is not None:
            slot = last_slot
            alternative_next = False
        elif context == "plural_definite":
            slot = definite_plural_slot
        elif context == "plural":
            slot = plural_slot
            context = "after_plural"
        elif not seen_singular_form:
            slot = singular_slot
            seen_singular_form = True
        else:
            slot = plural_slot
            context = "after_plural"

        result.extend(SlotOperation(slot, raw, operation) for operation in operations)
        last_slot = slot
        pending_best = False

    if not saw_notation_marker:
        return None
    return tuple(result) if result else None


def _best_overlap_replacement(base: str, tail: str) -> tuple[str | None, int]:
    best_index = -1
    best_score = 0
    folded_base = base.casefold()
    folded_tail = tail.casefold()
    for index in range(len(base)):
        score = 0
        while (
            index + score < len(base)
            and score < len(tail)
            and folded_base[index + score] == folded_tail[score]
        ):
            score += 1
        if score > best_score:
            best_index = index
            best_score = score
    if best_index < 0:
        return None, 0
    return base[:best_index] + tail, best_score


def apply_form_operation(
    base: str,
    operation: FormOperation,
    *,
    append: Callable[[str, str], str | None] | None = None,
    replace_tail: Callable[[str, str], str | None] | None = None,
) -> str | None:
    if operation.kind is FormOperationKind.UNCHANGED:
        return base
    if operation.kind is FormOperationKind.EXPLICIT:
        return operation.value
    if operation.kind is FormOperationKind.APPEND:
        return append(base, operation.value) if append else base + operation.value
    if operation.kind is FormOperationKind.REPLACE_TAIL:
        overlap, score = _best_overlap_replacement(base, operation.value)
        if score >= 2:
            return overlap
        return replace_tail(base, operation.value) if replace_tail else None
    return None


def split_alternative_branches(text: str) -> tuple[NotationBranch, ...]:
    cleaned = _clean_notation_spelling(text)
    branches: list[NotationBranch] = []
    for branch_text in re.split(r"\s+_\s+", cleaned):
        branch_text = branch_text.strip()
        if not branch_text:
            return ()
        tokens = tokenize_notation(branch_text)
        if tokens is None:
            return ()
        branches.append(NotationBranch(branch_text, tokens))
    return tuple(branches)


def split_forms(text: str) -> tuple[str, ...]:
    normalized = normalize_notation(text)
    normalized = normalized.replace(",", " ").replace(";", " ")
    return tuple(
        token
        for token in normalized.split()
        if token not in {"el.", "h", "_", "och"}
    )
