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


_ALTERNATIVE_RELATIONS = {
    "el.": "alternative",
    "h": "preferred_over",
    "ibl.": "occasional_alternative",
}


@dataclass(frozen=True)
class SlotOperation:
    """One independent form operation assigned to a grammatical slot.

    ``alternative_marker`` preserves the source marker without changing the
    primitive form operation.  The marker also carries editorial semantics:
    Språkbanken's ``H`` represents SAOL's printed ``hellre än`` and therefore
    means that the preceding realization is preferred over this one.  ``el.``
    is a neutral alternative and ``ibl.`` an occasional alternative.
    """

    slot: str
    token: str
    operation: FormOperation
    alternative_marker: str | None = None

    @property
    def alternative_relation(self) -> str | None:
        """Return normalized editorial relation for an alternative marker."""

        if self.alternative_marker is None:
            return None
        return _ALTERNATIVE_RELATIONS.get(self.alternative_marker.casefold())


@dataclass(frozen=True)
class SlotBranch:
    """One ``_`` branch after every form token has been assigned independently."""

    text: str
    tokens: tuple[str, ...]
    operations: tuple[SlotOperation, ...]


DIRECT_FORM_OPERATION_KINDS = frozenset(
    {
        FormOperationKind.UNCHANGED,
        FormOperationKind.APPEND,
        FormOperationKind.EXPLICIT,
    }
)


def is_direct_form_operation(operation: FormOperation) -> bool:
    return operation.kind in DIRECT_FORM_OPERATION_KINDS


_BRACKET_COMMENT = re.compile(r"\s*\[[^\]]*\]")
_HTML_TAG = re.compile(r"</?[^>]+>")
_GLUED_LABEL_OPERATION = re.compile(r"(?<!\w)([A-Za-zÅÄÖåäöÉéÜü]+\.)(?=[+\-])")
_SPLIT_REPLACEMENT_OPERATION = re.compile(r"(?<!\S)-\s+(?=[0-9A-Za-zÅÄÖåäöÉéÜü])")
_FORM_PAYLOAD = re.compile(r"[^\s;,_]+")
_EXPLICIT_FORM = re.compile(r"[^\s;,+_]+")
_OPTIONAL_FORM_TOKEN = re.compile(r"^([^()]*)\(([^()]+)\)([^()]*)$")
_NOTATION_TOKEN_RE = re.compile(r"pl\.|best\.|el\.|[;,]|[+\-][^\s;,_]*|[^\s;,+_]+", re.IGNORECASE)
_SOURCE_TEXT_LIMIT = 50


def _drop_untrusted_final_token(text: str) -> str:
    if len(text) != _SOURCE_TEXT_LIMIT:
        return text
    stripped = text.rstrip()
    prefix, separator, _last = stripped.rpartition(" ")
    if not separator:
        return ""
    prefix = prefix.rstrip()
    if prefix.casefold().endswith(" el."):
        prefix = prefix[:-4].rstrip()
    return prefix


def _clean_notation_spelling(text: str) -> str:
    text = _drop_untrusted_final_token(text)
    without_tags = _HTML_TAG.sub("", text)
    without_brackets = _BRACKET_COMMENT.sub("", without_tags)
    with_label_boundaries = _GLUED_LABEL_OPERATION.sub(r"\1 ", without_brackets)
    # A standalone '-' is never a valid form operation. Språkbanken rows can
    # contain export spacing such as ``pl.- rodren``. Join the sign to its
    # lexical payload so the ordinary replacement parser sees ``-rodren``.
    with_replacement_payloads = _SPLIT_REPLACEMENT_OPERATION.sub("-", with_label_boundaries)
    return " ".join(with_replacement_payloads.split())


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


def expand_optional_form_token(token: str) -> tuple[str, ...]:
    raw = token.strip()
    match = _OPTIONAL_FORM_TOKEN.fullmatch(raw)
    if match is None:
        return (raw,)
    before, optional, after = match.groups()
    variants = (before + after, before + optional + after)
    return tuple(dict.fromkeys(variants))


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
    operations: list[FormOperation] = []
    for variant in expand_optional_form_token(_unwrap_token(token)):
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
    """Assign each form token independently to a grammatical slot.

    Labels change only the current slot. ``el.``, ``H`` and ``ibl.`` make the
    next form another realization of the previous slot. ``H`` specifically
    preserves the SAOL relation ``hellre än`` (preferred over), rather than a
    neutral alternative. ``_`` is handled one level above this function and
    merely starts another branch.
    """

    result: list[SlotOperation] = []
    context = "singular"
    pending_best = False
    seen_singular_form = False
    last_slot: str | None = None
    alternative_marker: str | None = None
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
        if lower in {"el.", "h", "ibl."}:
            saw_notation_marker = True
            alternative_marker = lower if last_slot is not None else None
            continue
        if lower == "best.":
            saw_notation_marker = True
            pending_best = True
            alternative_marker = None
            continue
        if lower == "pl.":
            saw_notation_marker = True
            context = "plural_definite" if pending_best else "plural"
            pending_best = False
            alternative_marker = None
            continue
        if _is_comment_word(raw) or _is_generic_label(raw):
            saw_notation_marker = True
            continue

        operations = parse_form_operations(raw)
        if operations is None:
            return None
        if any(operation.kind is not FormOperationKind.EXPLICIT for operation in operations):
            saw_notation_marker = True

        marker_for_token = alternative_marker
        if alternative_marker is not None and last_slot is not None:
            slot = last_slot
            alternative_marker = None
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

        result.extend(
            SlotOperation(slot, raw, operation, marker_for_token)
            for operation in operations
        )
        last_slot = slot
        pending_best = False

    if not saw_notation_marker:
        return None
    return tuple(result) if result else None


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


def assign_notation_branches(
    text: str,
    *,
    singular_slot: str,
    plural_slot: str,
    definite_plural_slot: str,
    ignored_markers: frozenset[str] = frozenset(),
) -> tuple[SlotBranch, ...] | None:
    """Parse complete SAOL notation without recognizing whole paradigms.

    This is the common structural pipeline for all word classes: ``_`` creates
    independent branches, labels select slots, alternative markers reuse the
    preceding slot, and every remaining form token becomes one primitive
    ``FormOperation``. Word-class code supplies only the slot names and how an
    operation is applied to a base spelling.
    """

    branches = split_alternative_branches(text)
    if not branches:
        return None
    result: list[SlotBranch] = []
    for branch in branches:
        operations = assign_labeled_slots(
            branch.tokens,
            singular_slot=singular_slot,
            plural_slot=plural_slot,
            definite_plural_slot=definite_plural_slot,
            ignored_markers=ignored_markers,
        )
        if operations is None:
            return None
        result.append(SlotBranch(branch.text, branch.tokens, operations))
    return tuple(result)


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


def split_forms(text: str) -> tuple[str, ...]:
    normalized = normalize_notation(text)
    normalized = normalized.replace(",", " ").replace(";", " ")
    return tuple(token for token in normalized.split() if token not in {"el.", "h", "ibl.", "_", "och"})
