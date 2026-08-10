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
from .saol_slot_interpreter import (
    SlotGrammar,
    interpret_single_slot_sequence,
    interpret_slot_branches,
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


def _dedupe_forms(forms: list[AdjectiveForm]) -> tuple[AdjectiveForm, ...]:
    deduped: list[AdjectiveForm] = []
    seen: set[tuple[str, str]] = set()
    for form in forms:
        marker = (form.written_form, form.slot)
        if marker not in seen:
            deduped.append(form)
            seen.add(marker)
    return tuple(deduped)


def _single_operation(token: str) -> FormOperation | None:
    parsed = parse_form_operations(token)
    if parsed is None or len(parsed) != 1:
        return None
    return parsed[0]


def interpret_unlabelled_positive_adjective_slots(
    record: dict[str, Any],
) -> AdjectiveSlots | None:
    """Interpret one/two unlabelled positive ADJ form operations structurally."""

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
        operation = _single_operation(token)
        if operation is None:
            return None
        operations.append(operation)

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

    return AdjectiveSlots(
        lemma=lemma,
        forms=_dedupe_forms(forms),
        rule="structural_positive_sequence",
    )


def _labelled_positive_implicit_slot(
    index: int,
    last_slot: str | None,
    _operation: FormOperation,
) -> str | None:
    if index == 0:
        return "neuter_singular"
    if last_slot == "neuter_singular":
        return "definite_or_plural"
    return None


_ADJECTIVE_POSITIVE_LABEL_GRAMMAR = SlotGrammar(
    label_slots={
        "n.": "neuter_singular",
        "neutr.": "neuter_singular",
        "pl.": "definite_or_plural",
        "best.": "definite_or_plural",
        "mask.": "masculine_definite",
    },
    implicit_slot=_labelled_positive_implicit_slot,
    alternative_markers=frozenset({"el."}),
    transparent_markers=frozenset({"och:"}),
    require_marker=True,
)


def interpret_labelled_positive_adjective_slots(
    record: dict[str, Any],
) -> AdjectiveSlots | None:
    """Interpret positive ADJ labels with the shared word-class-neutral engine."""

    lemma = _value(record, "normaliserat_ord").casefold()
    raw_text = _value(record, "text")
    if not lemma or " " in lemma or not lemma.isalpha() or not raw_text:
        return None

    operations = interpret_single_slot_sequence(
        raw_text,
        _ADJECTIVE_POSITIVE_LABEL_GRAMMAR,
    )
    if operations is None:
        return None

    forms: list[AdjectiveForm] = [AdjectiveForm(lemma, "common_singular")]
    for item in operations:
        value = _apply_positive_operation(
            lemma,
            item.operation,
            neuter=item.slot == "neuter_singular",
        )
        if value is None:
            return None
        forms.append(AdjectiveForm(value, item.slot))

    return AdjectiveSlots(
        lemma=lemma,
        forms=_dedupe_forms(forms),
        rule="structural_labelled_positive_slots",
    )


def _common_from_neuter_for_e_plural(neuter: str) -> str | None:
    """Invert the productive ``-ad -> -at`` positive relation when evidenced."""

    if not neuter.endswith("at"):
        return None
    return neuter[:-2] + "ad"


def _parallel_positive_implicit_slot(
    index: int,
    _last_slot: str | None,
    _operation: FormOperation,
) -> str | None:
    if index == 0:
        return "neuter_singular"
    if index == 1:
        return "definite_or_plural"
    return None


_ADJECTIVE_PARALLEL_POSITIVE_GRAMMAR = SlotGrammar(
    label_slots={},
    implicit_slot=_parallel_positive_implicit_slot,
)


def interpret_parallel_positive_adjective_slots(
    record: dict[str, Any],
) -> AdjectiveSlots | None:
    """Interpret independent ``_`` branches through the shared branch engine."""

    lemma = _value(record, "normaliserat_ord").casefold()
    raw_text = _value(record, "text")
    if not lemma or " " in lemma or not lemma.isalpha() or " _ " not in f" {raw_text} ":
        return None

    branches = interpret_slot_branches(
        raw_text,
        _ADJECTIVE_PARALLEL_POSITIVE_GRAMMAR,
    )
    if branches is None or len(branches) < 2:
        return None

    forms: list[AdjectiveForm] = [AdjectiveForm(lemma, "common_singular")]
    for branch in branches:
        if len(branch.operations) != 2:
            return None
        neuter_item, plural_item = branch.operations
        if (
            neuter_item.slot != "neuter_singular"
            or plural_item.slot != "definite_or_plural"
        ):
            return None

        neuter_operation = neuter_item.operation
        plural_operation = plural_item.operation

        # Relative neuter + explicit variant form may introduce a different
        # branch lemma (e.g. +t schangdobla). Without independent evidence for
        # that lemma this layer must fall back rather than attach it to the
        # primary article lemma.
        if (
            neuter_operation.kind in {FormOperationKind.APPEND, FormOperationKind.UNCHANGED}
            and plural_operation.kind is FormOperationKind.EXPLICIT
        ):
            return None

        neuter = _apply_positive_operation(lemma, neuter_operation, neuter=True)
        if neuter is None:
            return None

        branch_common: str | None = None
        if (
            plural_operation.kind is FormOperationKind.APPEND
            and plural_operation.value.casefold() == "e"
            and neuter_operation.kind
            in {FormOperationKind.EXPLICIT, FormOperationKind.REPLACE_TAIL}
        ):
            branch_common = _common_from_neuter_for_e_plural(neuter)
            if branch_common is None:
                return None

        plural_base = branch_common or lemma
        definite = _apply_positive_operation(
            plural_base,
            plural_operation,
            neuter=False,
        )
        if definite is None:
            return None

        if branch_common is not None:
            forms.append(AdjectiveForm(branch_common, "common_singular"))
        forms.extend(
            (
                AdjectiveForm(neuter, "neuter_singular"),
                AdjectiveForm(definite, "definite_or_plural"),
            )
        )

    return AdjectiveSlots(
        lemma=lemma,
        forms=_dedupe_forms(forms),
        rule="structural_parallel_positive_branches",
    )


def interpret_adjective_row(record: dict[str, Any]) -> AdjectiveSlots | None:
    """Prefer structural clean-room interpretation, then the legacy coverage path."""

    return (
        interpret_unlabelled_positive_adjective_slots(record)
        or interpret_labelled_positive_adjective_slots(record)
        or interpret_parallel_positive_adjective_slots(record)
        or interpret_simple_adjective_slots(record)
    )
