from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping

from .saol_notation import (
    FormOperation,
    FormOperationKind,
    SlotBranch,
    SlotOperation,
    parse_form_operations,
    split_alternative_branches,
)


ImplicitSlotResolver = Callable[[int, str | None, FormOperation], str | None]


@dataclass(frozen=True)
class SlotGrammar:
    """Word-class configuration for the shared SAOL slot interpreter.

    The notation engine owns tokenization, ``_`` branches, labels and alternative
    markers. A word class supplies only the mapping from labels to grammatical
    slots plus the slot to use when a form operation is intentionally unlabelled.
    """

    label_slots: Mapping[str, str]
    implicit_slot: ImplicitSlotResolver
    alternative_markers: frozenset[str] = frozenset({"el.", "h", "ibl."})
    transparent_markers: frozenset[str] = frozenset({"i:", "som:", "används:", "anv."})
    punctuation: frozenset[str] = frozenset({",", ";"})
    require_marker: bool = False
    bare_label_as_unchanged: bool = False


_EDITORIAL_USAGE_MARKERS = frozenset({
    "högt.",
    "vanl.",
    "åld.",
    "t.ex.",
    "f.",
})


def _clean_token(token: str) -> str:
    return token.strip().strip("()").casefold()


def is_editorial_usage_marker(token: str) -> bool:
    lower = _clean_token(token)
    return lower.endswith(":") or lower in _EDITORIAL_USAGE_MARKERS


def assign_slots_with_grammar(
    tokens: tuple[str, ...],
    grammar: SlotGrammar,
) -> tuple[SlotOperation, ...] | None:
    """Assign primitive SAOL form operations to slots without paradigm regexes."""

    result: list[SlotOperation] = []
    selected_slot: str | None = None
    last_slot: str | None = None
    alternative_marker: str | None = None
    form_index = 0
    saw_marker = False

    for token in tokens:
        lower = _clean_token(token)
        if token in grammar.punctuation:
            continue
        if lower in grammar.transparent_markers or is_editorial_usage_marker(token):
            saw_marker = True
            continue
        if lower in grammar.alternative_markers:
            if last_slot is None:
                return None
            selected_slot = last_slot
            alternative_marker = lower
            saw_marker = True
            continue
        if lower in grammar.label_slots:
            selected_slot = grammar.label_slots[lower]
            alternative_marker = None
            saw_marker = True
            continue
        if lower.endswith((":", ".")) and not lower.startswith(("+", "-")):
            return None

        operations = parse_form_operations(token)
        if operations is None:
            return None
        if any(operation.kind is not FormOperationKind.EXPLICIT for operation in operations):
            saw_marker = True

        token_slot = selected_slot
        if token_slot is None:
            token_slot = grammar.implicit_slot(form_index, last_slot, operations[0])
        if token_slot is None:
            return None

        for operation in operations:
            result.append(
                SlotOperation(
                    slot=token_slot,
                    token=token,
                    operation=operation,
                    alternative_marker=alternative_marker,
                )
            )
        last_slot = token_slot
        if alternative_marker is None:
            form_index += 1
        selected_slot = None
        alternative_marker = None

    # A dangling label or alternative is incomplete notation. Source-level
    # truncation handling decides whether a complete prefix may still be used;
    # the ordinary shared grammar never silently accepts the missing form.
    if selected_slot is not None:
        if grammar.bare_label_as_unchanged and not result and alternative_marker is None:
            result.append(
                SlotOperation(
                    slot=selected_slot,
                    token="+",
                    operation=FormOperation(FormOperationKind.UNCHANGED, source="+"),
                )
            )
            selected_slot = None
            saw_marker = True
        else:
            return None
    if grammar.require_marker and not saw_marker:
        return None
    return tuple(result) if result else None


def interpret_slot_branches(
    text: str,
    grammar: SlotGrammar,
) -> tuple[SlotBranch, ...] | None:
    branches = split_alternative_branches(text)
    if not branches:
        return None
    result: list[SlotBranch] = []
    for branch in branches:
        operations = assign_slots_with_grammar(branch.tokens, grammar)
        if operations is None:
            return None
        result.append(SlotBranch(branch.text, branch.tokens, operations))
    return tuple(result)


def interpret_single_slot_sequence(
    text: str,
    grammar: SlotGrammar,
) -> tuple[SlotOperation, ...] | None:
    branches = split_alternative_branches(text)
    if len(branches) != 1:
        return None
    return assign_slots_with_grammar(branches[0].tokens, grammar)
