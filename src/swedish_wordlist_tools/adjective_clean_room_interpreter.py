from __future__ import annotations

from typing import Any

from .adjective_row_interpreter import interpret_adjective_row as interpret_existing_adjective_row
from .adjective_slots import AdjectiveForm, AdjectiveSlots, _neuter_t
from .saol_notation import FormOperation, FormOperationKind, apply_form_operation
from .saol_slot_interpreter import SlotGrammar, interpret_slot_branches


def _value(record: dict[str, Any], key: str) -> str:
    value = record.get(key)
    return "" if value is None or str(value) == "(null)" else str(value).strip()


def _append_positive(base: str, suffix: str, *, neuter: bool) -> str | None:
    if not suffix or not suffix.isalpha():
        return None
    if neuter and suffix == "t":
        return _neuter_t(base)
    return base + suffix


def _apply_operation(base: str, operation: FormOperation, *, neuter: bool) -> str | None:
    return apply_form_operation(
        base,
        operation,
        append=lambda word, suffix: _append_positive(word, suffix, neuter=neuter),
    )


def _implicit_parallel_slot(
    index: int,
    _last_slot: str | None,
    _operation: FormOperation,
) -> str | None:
    if index == 0:
        return "neuter_singular"
    if index == 1:
        return "definite_or_plural"
    return None


_PARALLEL_GRAMMAR = SlotGrammar(label_slots={}, implicit_slot=_implicit_parallel_slot)


def _suffix_change(source: str, target: str) -> tuple[str, str] | None:
    """Return the minimal evidenced suffix replacement source -> target.

    The common prefix is evidence shared by both written forms.  Requiring both
    suffixes to be non-empty keeps this mechanism to replacement analogies rather
    than inventing arbitrary deletion/insertion rules.
    """

    limit = min(len(source), len(target))
    index = 0
    while index < limit and source[index] == target[index]:
        index += 1
    old_suffix = source[index:]
    new_suffix = target[index:]
    if not old_suffix or not new_suffix:
        return None
    return old_suffix, new_suffix


def _invert_suffix_change(
    surface: str,
    old_suffix: str,
    new_suffix: str,
) -> str | None:
    if not surface.endswith(new_suffix):
        return None
    stem = surface[: -len(new_suffix)]
    candidate = stem + old_suffix
    return candidate if candidate.isalpha() else None


def interpret_analogical_parallel_adjective_slots(
    record: dict[str, Any],
) -> AdjectiveSlots | None:
    """Infer parallel variant lemmas from an evidenced branch-to-branch analogy.

    Example::

        sjangdobel: +t sjangdobla _ +t schangdobla

    The first branch explicitly establishes the surface relation
    ``sjangdobel -> sjangdobla``.  Its minimal suffix replacement is then
    inverted on ``schangdobla`` to recover ``schangdobel``.  No spelling,
    suffix, or lemma is hard-coded; the relation must be demonstrated by the
    first branch itself.
    """

    lemma = _value(record, "normaliserat_ord").casefold()
    raw_text = _value(record, "text")
    if not lemma or " " in lemma or not lemma.isalpha() or " _ " not in f" {raw_text} ":
        return None

    branches = interpret_slot_branches(raw_text, _PARALLEL_GRAMMAR)
    if branches is None or len(branches) < 2:
        return None

    parsed: list[tuple[FormOperation, FormOperation]] = []
    for branch in branches:
        if len(branch.operations) != 2:
            return None
        neuter_item, plural_item = branch.operations
        if (
            neuter_item.slot != "neuter_singular"
            or plural_item.slot != "definite_or_plural"
            or neuter_item.operation.kind not in {FormOperationKind.APPEND, FormOperationKind.UNCHANGED}
            or plural_item.operation.kind is not FormOperationKind.EXPLICIT
        ):
            return None
        parsed.append((neuter_item.operation, plural_item.operation))

    first_neuter_operation, first_plural_operation = parsed[0]
    first_plural = first_plural_operation.value.casefold()
    first_neuter = _apply_operation(lemma, first_neuter_operation, neuter=True)
    if first_neuter is None:
        return None

    change = _suffix_change(lemma, first_plural)
    if change is None:
        return None
    old_suffix, new_suffix = change

    forms: list[AdjectiveForm] = [
        AdjectiveForm(lemma, "common_singular"),
        AdjectiveForm(first_neuter, "neuter_singular"),
        AdjectiveForm(first_plural, "definite_or_plural"),
    ]
    seen_common = {lemma}

    for neuter_operation, plural_operation in parsed[1:]:
        # Parallel branches must expose the same structural neuter instruction;
        # otherwise the first branch is not evidence for the second one.
        if neuter_operation != first_neuter_operation:
            return None
        plural = plural_operation.value.casefold()
        common = _invert_suffix_change(plural, old_suffix, new_suffix)
        if common is None or common in seen_common:
            return None
        # Verify that the inferred common form reproduces the explicit branch
        # surface under exactly the evidenced suffix replacement.
        if not common.endswith(old_suffix):
            return None
        reproduced = common[: -len(old_suffix)] + new_suffix
        if reproduced != plural:
            return None
        neuter = _apply_operation(common, neuter_operation, neuter=True)
        if neuter is None:
            return None
        forms.extend(
            (
                AdjectiveForm(common, "common_singular"),
                AdjectiveForm(neuter, "neuter_singular"),
                AdjectiveForm(plural, "definite_or_plural"),
            )
        )
        seen_common.add(common)

    return AdjectiveSlots(
        lemma=lemma,
        forms=tuple(forms),
        rule="structural_parallel_analogical_branches",
    )


def interpret_adjective_row(record: dict[str, Any]) -> AdjectiveSlots | None:
    """Canonical clean-room ADJ interpreter with conservative legacy fallback."""

    structural_parallel = interpret_analogical_parallel_adjective_slots(record)
    existing = interpret_existing_adjective_row(record)
    if structural_parallel is not None:
        # Use the analogical result only for the old branch family it replaces.
        # Other already-structural branch interpretations stay authoritative.
        if existing is None or existing.rule == "generic_parallel_slots":
            return structural_parallel
    return existing
