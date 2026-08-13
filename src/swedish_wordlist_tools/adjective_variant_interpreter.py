from __future__ import annotations

from typing import Any

from .adjective_clean_room_interpreter import (
    _PARALLEL_GRAMMAR,
    _apply_operation,
    interpret_adjective_row as interpret_clean_room_adjective_row,
)
from .adjective_slots import AdjectiveForm, AdjectiveSlots
from .saol_notation import FormOperationKind
from .saol_slot_interpreter import interpret_slot_branches


def _value(record: dict[str, Any], key: str) -> str:
    value = record.get(key)
    return "" if value is None or str(value) == "(null)" else str(value).strip()


def interpret_explicit_parallel_variant(record: dict[str, Any]) -> AdjectiveSlots | None:
    """Interpret two parallel ADJ branches using an explicitly evidenced variant base."""

    lemma = _value(record, "normaliserat_ord").casefold()
    alternative = _value(record, "_saol_alternative_lemma").casefold()
    raw_text = _value(record, "text")
    if not lemma or not alternative or lemma == alternative:
        return None

    branches = interpret_slot_branches(raw_text, _PARALLEL_GRAMMAR)
    if branches is None or len(branches) != 2:
        return None

    bases = (lemma, alternative)
    forms: list[AdjectiveForm] = []
    for base, branch in zip(bases, branches):
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
        neuter = _apply_operation(base, neuter_item.operation, neuter=True)
        if neuter is None:
            return None
        forms.extend(
            (
                AdjectiveForm(base, "common_singular"),
                AdjectiveForm(neuter, "neuter_singular"),
                AdjectiveForm(plural_item.operation.value.casefold(), "definite_or_plural"),
            )
        )

    return AdjectiveSlots(
        lemma=lemma,
        forms=tuple(forms),
        rule="structural_parallel_explicit_variant",
    )


def interpret_adjective_row(record: dict[str, Any]) -> AdjectiveSlots | None:
    explicit = interpret_explicit_parallel_variant(record)
    if explicit is not None:
        return explicit
    return interpret_clean_room_adjective_row(record)
