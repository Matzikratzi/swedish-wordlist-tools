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
    transparent_markers: frozenset[str] = frozenset()
    punctuation: frozenset[str] = frozenset({",", ";"})
    require_marker: bool = False


def _clean_token(token: str) -> str:
    return token.strip().strip("()").casefold()


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
        if lower in grammar.transparent_markers:
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
        # Relative SAOL operations are notation in their own right. A sequence
        # such as ``+en +ar`` or ``+n -hackor`` therefore needs no label or
        # punctuation marker to be structurally valid. Fully written EXPLICIT
        # forms remain unmarked so a word class can apply its own source-context
        # safety gate before accepting plain lexical text as inflection.
        if any(operation.kind is not FormOperationKind.EXPLICIT for operation in operations):
            saw_marker = True

        # One source token denotes one grammatical slot even when optional
        # spelling expands it to several primitive operations. Thus ``+(e)n``
        # yields ``+n`` and ``+en`` as alternative realizations of the same slot,
        # rather than advancing the implicit slot sequence between the variants.
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
        form_index += 1
        selected_slot = None
        alternative_marker = None

    if selected_slot is not None:
        return None
    if grammar.require_marker and not saw_marker:
        return None
    return tuple(result) if result else None


def interpret_slot_branches(
    text: str,
    grammar: SlotGrammar,
) -> tuple[SlotBranch, ...] | None:
    """Parse ``text`` into independent ``_`` branches using one slot grammar."""

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
    """Convenience wrapper for notation that must not contain ``_`` branches."""

    branches = split_alternative_branches(text)
    if len(branches) != 1:
        return None
    return assign_slots_with_grammar(branches[0].tokens, grammar)
