from __future__ import annotations

from typing import Any

from .adjective_row_interpreter import interpret_adjective_row as interpret_existing_adjective_row
from .adjective_slots import AdjectiveForm, AdjectiveSlots, _neuter_t
from .saol_notation import FormOperation, FormOperationKind, apply_form_operation
from .saol_slot_interpreter import SlotGrammar, interpret_single_slot_sequence, interpret_slot_branches


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


def _implicit_sequence_slot(
    index: int,
    _last_slot: str | None,
    _operation: FormOperation,
) -> str | None:
    slots = (
        "neuter_singular",
        "definite_or_plural",
        "comparative",
        "superlative",
    )
    return slots[index] if index < len(slots) else None


def _implicit_single_slot(
    index: int,
    _last_slot: str | None,
    operation: FormOperation,
) -> str | None:
    if index != 0:
        return None
    return (
        "definite_or_plural"
        if operation.kind is FormOperationKind.EXPLICIT
        else "neuter_singular"
    )


_SEQUENCE_GRAMMAR = SlotGrammar(label_slots={}, implicit_slot=_implicit_sequence_slot)
_SINGLE_GRAMMAR = SlotGrammar(label_slots={}, implicit_slot=_implicit_single_slot)


def interpret_shared_unlabelled_adjective_slots(
    record: dict[str, Any],
) -> AdjectiveSlots | None:
    """Interpret ordinary unlabelled adjective atom sequences through the shared engine.

    Multi-atom sequences use pure positional slots.  A lone atom is a separate
    grammatical contract: SAOL's operation role is itself sufficient evidence,
    with a relative operation denoting neuter and a fully written explicit form
    denoting definite/plural.  The distinction is structural and independent of
    any particular adjective spelling.
    """

    lemma = _value(record, "normaliserat_ord").casefold()
    raw_text = _value(record, "text")
    if not lemma or " " in lemma or not lemma.isalpha() or not raw_text or "_" in raw_text:
        return None

    operations = interpret_single_slot_sequence(raw_text, _SEQUENCE_GRAMMAR)
    if operations is None or len(operations) not in {1, 2, 4}:
        return None

    if len(operations) == 1:
        operations = interpret_single_slot_sequence(raw_text, _SINGLE_GRAMMAR)
        if operations is None or len(operations) != 1:
            return None
        expected_slots = (
            "definite_or_plural",
        ) if operations[0].operation.kind is FormOperationKind.EXPLICIT else (
            "neuter_singular",
        )
    elif len(operations) == 2:
        expected_slots = ("neuter_singular", "definite_or_plural")
    else:
        expected_slots = (
            "neuter_singular",
            "definite_or_plural",
            "comparative",
            "superlative",
        )
    if tuple(item.slot for item in operations) != expected_slots:
        return None

    forms: list[AdjectiveForm] = [AdjectiveForm(lemma, "common_singular")]
    for item in operations:
        value = _apply_operation(
            lemma,
            item.operation,
            neuter=item.slot == "neuter_singular",
        )
        if value is None:
            return None
        form = AdjectiveForm(value, item.slot)
        if form not in forms:
            forms.append(form)

    return AdjectiveSlots(
        lemma=lemma,
        forms=tuple(forms),
        rule=(
            "shared_full_adjective_atoms"
            if len(operations) == 4
            else "shared_positive_atoms"
        ),
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
    """Return the minimal evidenced suffix replacement source -> target."""

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
    """Infer parallel variant lemmas from an evidenced branch-to-branch analogy."""

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
        if neuter_operation != first_neuter_operation:
            return None
        plural = plural_operation.value.casefold()
        common = _invert_suffix_change(plural, old_suffix, new_suffix)
        if common is None or common in seen_common:
            return None
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

    shared_unlabelled = interpret_shared_unlabelled_adjective_slots(record)
    if shared_unlabelled is not None:
        return shared_unlabelled

    structural_parallel = interpret_analogical_parallel_adjective_slots(record)
    existing = interpret_existing_adjective_row(record)
    if structural_parallel is not None:
        if existing is None or existing.rule == "generic_parallel_slots":
            return structural_parallel
    return existing
