from __future__ import annotations

from typing import Any

from .adjective_slots import (
    AdjectiveForm,
    AdjectiveSlots,
    _neuter_t,
    interpret_simple_adjective_slots,
)
from .saol_notation import (
    FormOperation,
    FormOperationKind,
    apply_form_operation,
    normalize_notation,
    parse_form_operations,
    tokenize_notation,
)


def _value(record: dict[str, Any], key: str) -> str:
    value = record.get(key)
    return "" if value is None or str(value) == "(null)" else str(value).strip()


def _append_positive(base: str, suffix: str, *, neuter: bool) -> str | None:
    if not suffix or not suffix.isalpha():
        return None
    if neuter and suffix == "t":
        return _neuter_t(base)
    return base + suffix


def _apply_positive_operation(
    lemma: str,
    operation: FormOperation,
    *,
    neuter: bool,
) -> str | None:
    return apply_form_operation(
        lemma,
        operation,
        append=lambda base, suffix: _append_positive(base, suffix, neuter=neuter),
    )


def interpret_unlabelled_positive_adjective_slots(
    record: dict[str, Any],
) -> AdjectiveSlots | None:
    """Interpret one/two unlabelled positive ADJ form operations structurally.

    This deliberately knows nothing about particular suffix strings. A two-form
    sequence assigns the first independent operation to neuter singular and the
    second to definite/plural. A single explicit word is an additional
    definite/plural form, while a single relative operation fills neuter.

    Labels, comparison, usage restrictions and ``_`` branches are left to the
    broader adjective interpreter for now. That makes this a conservative first
    clean-room layer: anything it cannot prove falls back unchanged.
    """

    lemma = _value(record, "normaliserat_ord").casefold()
    raw_text = _value(record, "text")
    if not lemma or " " in lemma or not lemma.isalpha() or not raw_text:
        return None

    text = normalize_notation(raw_text)
    tokens = tokenize_notation(text)
    if tokens is None or len(tokens) not in {1, 2}:
        return None

    operations: list[FormOperation] = []
    for token in tokens:
        parsed = parse_form_operations(token)
        if parsed is None or len(parsed) != 1:
            return None
        operations.append(parsed[0])

    forms: list[AdjectiveForm] = [AdjectiveForm(lemma, "common_singular")]
    if len(operations) == 1:
        operation = operations[0]
        slot = (
            "definite_or_plural"
            if operation.kind is FormOperationKind.EXPLICIT
            else "neuter_singular"
        )
        value = _apply_positive_operation(
            lemma,
            operation,
            neuter=slot == "neuter_singular",
        )
        if value is None:
            return None
        forms.append(AdjectiveForm(value, slot))
    else:
        neuter = _apply_positive_operation(lemma, operations[0], neuter=True)
        definite = _apply_positive_operation(lemma, operations[1], neuter=False)
        if neuter is None or definite is None:
            return None
        forms.extend(
            (
                AdjectiveForm(neuter, "neuter_singular"),
                AdjectiveForm(definite, "definite_or_plural"),
            )
        )

    deduped: list[AdjectiveForm] = []
    seen: set[tuple[str, str]] = set()
    for form in forms:
        marker = (form.written_form, form.slot)
        if marker not in seen:
            deduped.append(form)
            seen.add(marker)
    return AdjectiveSlots(
        lemma=lemma,
        forms=tuple(deduped),
        rule="structural_positive_sequence",
    )


def interpret_adjective_row(record: dict[str, Any]) -> AdjectiveSlots | None:
    """Prefer structural clean-room interpretation, then the legacy coverage path."""

    return (
        interpret_unlabelled_positive_adjective_slots(record)
        or interpret_simple_adjective_slots(record)
    )
