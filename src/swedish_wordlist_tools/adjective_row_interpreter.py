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
    split_alternative_branches,
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


def interpret_labelled_positive_adjective_slots(
    record: dict[str, Any],
) -> AdjectiveSlots | None:
    """Interpret positive ADJ labels independently from form operations.

    Labels only select slots. ``el.`` makes the next operation another realization
    of the preceding slot. An initial unlabelled operation before a label is the
    neuter form, so e.g. ``-blått, best. och: pl. + el. +a`` is interpreted as
    four independent instructions rather than as one paradigm-shaped regex.

    Comparison labels, usage restrictions and ``_`` branches remain outside this
    layer for now.
    """

    lemma = _value(record, "normaliserat_ord").casefold()
    raw_text = _value(record, "text")
    if not lemma or " " in lemma or not lemma.isalpha() or not raw_text:
        return None

    text = normalize_notation(raw_text)
    if " _ " in f" {text} ":
        return None
    tokens = tokenize_notation(text)
    if tokens is None:
        return None

    slot_labels = {
        "n.": "neuter_singular",
        "neutr.": "neuter_singular",
        "pl.": "definite_or_plural",
        "best.": "definite_or_plural",
        "mask.": "masculine_definite",
    }
    forbidden = {
        "komp.",
        "superl.",
        "h",
        "ibl.",
    }

    forms: list[AdjectiveForm] = [AdjectiveForm(lemma, "common_singular")]
    selected_slot: str | None = None
    previous_slot: str | None = None
    saw_label = False
    saw_operation = False

    for token in tokens:
        lower = token.casefold()
        if token in {",", ";"}:
            continue
        if lower in forbidden:
            return None
        if lower == "och:":
            if not saw_label:
                return None
            continue
        if lower == "el.":
            if previous_slot is None:
                return None
            selected_slot = previous_slot
            saw_label = True
            continue
        if lower.endswith(":"):
            return None
        if lower in slot_labels:
            selected_slot = slot_labels[lower]
            saw_label = True
            continue

        operation = _single_operation(token)
        if operation is None:
            return None

        if selected_slot is not None:
            slot = selected_slot
            selected_slot = None
        elif not saw_operation:
            slot = "neuter_singular"
        elif previous_slot == "neuter_singular":
            slot = "definite_or_plural"
        else:
            return None

        value = _apply_positive_operation(
            lemma,
            operation,
            neuter=slot == "neuter_singular",
        )
        if value is None:
            return None
        forms.append(AdjectiveForm(value, slot))
        previous_slot = slot
        saw_operation = True

    if selected_slot is not None or not saw_label or not saw_operation:
        return None

    return AdjectiveSlots(
        lemma=lemma,
        forms=_dedupe_forms(forms),
        rule="structural_labelled_positive_slots",
    )


def _common_from_neuter_for_e_plural(neuter: str) -> str | None:
    """Invert the productive ``-ad -> -at`` positive relation when evidenced.

    This is word-class morphology, not a paradigm-specific spelling rule. It is
    used only when a branch explicitly supplies its neuter form and then ``+e``;
    the latter must be applied to that branch's common form rather than to the
    article's primary lemma.
    """

    if not neuter.endswith("at"):
        return None
    return neuter[:-2] + "ad"


def interpret_parallel_positive_adjective_slots(
    record: dict[str, Any],
) -> AdjectiveSlots | None:
    """Interpret independent ``_`` branches made of positive form operations.

    Each branch is tokenized separately. For the current conservative layer a
    branch contains exactly two operations: neuter and definite/plural. No whole
    two-branch regex is recognized. If ``+e`` follows an explicit/replaced
    ``-at`` neuter, the branch common form is recovered by ordinary adjective
    morphology so the suffix is applied to the branch rather than the primary
    lemma. More exotic branch evidence falls back to the legacy interpreter.
    """

    lemma = _value(record, "normaliserat_ord").casefold()
    raw_text = _value(record, "text")
    if not lemma or " " in lemma or not lemma.isalpha() or " _ " not in f" {raw_text} ":
        return None

    branches = split_alternative_branches(raw_text)
    if len(branches) < 2:
        return None

    forms: list[AdjectiveForm] = [AdjectiveForm(lemma, "common_singular")]
    for branch in branches:
        tokens = tuple(token for token in branch.tokens if token not in {",", ";"})
        if len(tokens) != 2:
            return None
        neuter_operation = _single_operation(tokens[0])
        plural_operation = _single_operation(tokens[1])
        if neuter_operation is None or plural_operation is None:
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
