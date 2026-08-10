from __future__ import annotations

import re
from typing import Any

from .adjective_slots import (
    AdjectiveForm,
    AdjectiveSlots,
    UsageRestriction,
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


def _compound_prefix(record: dict[str, Any], lemma: str) -> str:
    stycke = re.sub(r"<[^>]+>", "", _value(record, "stycke")).casefold()
    if "|" not in stycke:
        return ""
    prefix = "".join(stycke.split("|")[:-1])
    prefix = re.sub(r"^\d+", "", prefix)
    prefix = "".join(char for char in prefix if char.isalpha() or char == "-")
    return prefix if prefix and lemma.startswith(prefix) else ""


def interpret_unlabelled_positive_adjective_slots(record: dict[str, Any]) -> AdjectiveSlots | None:
    """Interpret unlabelled positive/comparison sequences by slot order."""
    lemma = _value(record, "normaliserat_ord").casefold()
    raw_text = _value(record, "text")
    if not lemma or " " in lemma or not lemma.isalpha() or not raw_text:
        return None
    text = normalize_notation(raw_text)
    tokens = tokenize_notation(text)
    if tokens is None:
        return None
    form_tokens = tuple(token for token in tokens if token not in {",", ";"})
    if len(form_tokens) not in {1, 2, 4}:
        return None
    operations: list[FormOperation] = []
    for token in form_tokens:
        operation = _single_operation(token)
        if operation is None:
            return None
        operations.append(operation)
    forms: list[AdjectiveForm] = [AdjectiveForm(lemma, "common_singular")]
    if len(operations) == 1:
        operation = operations[0]
        slot = "definite_or_plural" if operation.kind is FormOperationKind.EXPLICIT else "neuter_singular"
        value = _apply_positive_operation(lemma, operation, neuter=slot == "neuter_singular")
        if value is None:
            return None
        forms.append(AdjectiveForm(value, slot))
    else:
        slots = ("neuter_singular", "definite_or_plural")
        if len(operations) == 4:
            slots += ("comparative", "superlative")
        for operation, slot in zip(operations, slots):
            value = _apply_positive_operation(lemma, operation, neuter=slot == "neuter_singular")
            if value is None:
                return None
            forms.append(AdjectiveForm(value, slot))
    rule = "structural_full_adjective_sequence" if len(operations) == 4 else "structural_positive_sequence"
    return AdjectiveSlots(lemma=lemma, forms=_dedupe_forms(forms), rule=rule)


def _labelled_positive_implicit_slot(index: int, last_slot: str | None, _operation: FormOperation) -> str | None:
    if index == 0:
        return "neuter_singular"
    if last_slot == "neuter_singular":
        return "definite_or_plural"
    return None


_ADJECTIVE_POSITIVE_LABEL_GRAMMAR = SlotGrammar(
    label_slots={"n.": "neuter_singular", "neutr.": "neuter_singular", "pl.": "definite_or_plural", "best.": "definite_or_plural", "mask.": "masculine_definite"},
    implicit_slot=_labelled_positive_implicit_slot,
    alternative_markers=frozenset({"el."}),
    transparent_markers=frozenset({"och:"}),
    require_marker=True,
)


def interpret_labelled_positive_adjective_slots(record: dict[str, Any]) -> AdjectiveSlots | None:
    lemma = _value(record, "normaliserat_ord").casefold()
    raw_text = _value(record, "text")
    if not lemma or " " in lemma or not lemma.isalpha() or not raw_text:
        return None
    operations = interpret_single_slot_sequence(raw_text, _ADJECTIVE_POSITIVE_LABEL_GRAMMAR)
    if operations is None:
        return None
    forms: list[AdjectiveForm] = [AdjectiveForm(lemma, "common_singular")]
    for item in operations:
        value = _apply_positive_operation(lemma, item.operation, neuter=item.slot == "neuter_singular")
        if value is None:
            return None
        forms.append(AdjectiveForm(value, item.slot))
    return AdjectiveSlots(lemma=lemma, forms=_dedupe_forms(forms), rule="structural_labelled_positive_slots")


def _comparison_implicit_slot(index: int, last_slot: str | None, _operation: FormOperation) -> str | None:
    if index == 0:
        return "neuter_singular"
    if index == 1 and last_slot == "neuter_singular":
        return "definite_or_plural"
    return None


_ADJECTIVE_COMPARISON_GRAMMAR = SlotGrammar(
    label_slots={"komp.": "comparative", "superl.": "superlative"},
    implicit_slot=_comparison_implicit_slot,
    alternative_markers=frozenset({"el.", "h"}),
    require_marker=True,
)


def interpret_labelled_comparison_adjective_slots(record: dict[str, Any]) -> AdjectiveSlots | None:
    lemma = _value(record, "normaliserat_ord").casefold()
    raw_text = _value(record, "text")
    if not lemma or " " in lemma or not lemma.isalpha() or not raw_text:
        return None
    lowered = normalize_notation(raw_text)
    if "komp." not in lowered and "superl." not in lowered:
        return None
    operations = interpret_single_slot_sequence(raw_text, _ADJECTIVE_COMPARISON_GRAMMAR)
    if operations is None:
        return None
    forms: list[AdjectiveForm] = [AdjectiveForm(lemma, "common_singular")]
    for item in operations:
        value = _apply_positive_operation(lemma, item.operation, neuter=item.slot == "neuter_singular")
        if value is None:
            return None
        forms.append(AdjectiveForm(value, item.slot))
    return AdjectiveSlots(lemma=lemma, forms=_dedupe_forms(forms), rule="structural_labelled_comparison_slots")


def _unlabelled_comparison_alternative_slot(index: int, last_slot: str | None, _operation: FormOperation) -> str | None:
    if index == 0:
        return "neuter_singular"
    if index == 1 and last_slot == "neuter_singular":
        return "comparative"
    if index >= 3 and last_slot == "comparative":
        return "superlative"
    return None


_ADJECTIVE_UNLABELLED_COMPARISON_ALTERNATIVE_GRAMMAR = SlotGrammar(
    label_slots={},
    implicit_slot=_unlabelled_comparison_alternative_slot,
    alternative_markers=frozenset({"h"}),
    require_marker=True,
)


def interpret_unlabelled_comparison_alternatives(record: dict[str, Any]) -> AdjectiveSlots | None:
    lemma = _value(record, "normaliserat_ord").casefold()
    raw_text = _value(record, "text")
    if not lemma or " " in lemma or not lemma.isalpha() or " h " not in f" {normalize_notation(raw_text)} ":
        return None
    operations = interpret_single_slot_sequence(raw_text, _ADJECTIVE_UNLABELLED_COMPARISON_ALTERNATIVE_GRAMMAR)
    if operations is None:
        return None
    expected = ("neuter_singular", "comparative", "comparative", "superlative", "superlative")
    if tuple(item.slot for item in operations) != expected:
        return None
    forms: list[AdjectiveForm] = [AdjectiveForm(lemma, "common_singular")]
    for item in operations:
        value = _apply_positive_operation(lemma, item.operation, neuter=item.slot == "neuter_singular")
        if value is None:
            return None
        forms.append(AdjectiveForm(value, item.slot))
    return AdjectiveSlots(lemma=lemma, forms=_dedupe_forms(forms), rule="structural_unlabelled_comparison_alternatives")


def _same_slot_alternative_implicit_slot(index: int, _last_slot: str | None, operation: FormOperation) -> str | None:
    if index == 0 and operation.kind is FormOperationKind.EXPLICIT:
        return "definite_or_plural"
    return None


_ADJECTIVE_SAME_SLOT_ALTERNATIVE_GRAMMAR = SlotGrammar(
    label_slots={},
    implicit_slot=_same_slot_alternative_implicit_slot,
    alternative_markers=frozenset({"el."}),
    require_marker=True,
)


def interpret_unlabelled_adjective_alternatives(record: dict[str, Any]) -> AdjectiveSlots | None:
    lemma = _value(record, "normaliserat_ord").casefold()
    raw_text = _value(record, "text")
    if not lemma or " " in lemma or not lemma.isalpha() or "el." not in normalize_notation(raw_text):
        return None
    operations = interpret_single_slot_sequence(raw_text, _ADJECTIVE_SAME_SLOT_ALTERNATIVE_GRAMMAR)
    if operations is None:
        return None
    forms: list[AdjectiveForm] = [AdjectiveForm(lemma, "common_singular")]
    for item in operations:
        if item.slot != "definite_or_plural":
            return None
        value = _apply_positive_operation(lemma, item.operation, neuter=False)
        if value is None:
            return None
        forms.append(AdjectiveForm(value, item.slot))
    return AdjectiveSlots(lemma=lemma, forms=_dedupe_forms(forms), rule="structural_same_slot_alternatives")


def _partial_label_implicit_slot(index: int, _last_slot: str | None, _operation: FormOperation) -> str | None:
    if index == 0:
        return "masculine_definite"
    return None


_ADJECTIVE_PARTIAL_LABEL_GRAMMAR = SlotGrammar(
    label_slots={"superl.": "superlative"},
    implicit_slot=_partial_label_implicit_slot,
    transparent_markers=frozenset({"vard."}),
    require_marker=True,
)


def interpret_partial_labelled_adjective_slots(record: dict[str, Any]) -> AdjectiveSlots | None:
    lemma = _value(record, "normaliserat_ord").casefold()
    raw_text = _value(record, "text")
    if not lemma or " " in lemma or not lemma.isalpha() or "vard." not in normalize_notation(raw_text):
        return None
    operations = interpret_single_slot_sequence(raw_text, _ADJECTIVE_PARTIAL_LABEL_GRAMMAR)
    if operations is None or tuple(item.slot for item in operations) != ("masculine_definite", "superlative"):
        return None
    forms: list[AdjectiveForm] = [AdjectiveForm(lemma, "common_singular")]
    for item in operations:
        value = _apply_positive_operation(lemma, item.operation, neuter=False)
        if value is None:
            return None
        forms.append(AdjectiveForm(value, item.slot))
    return AdjectiveSlots(lemma=lemma, forms=_dedupe_forms(forms), rule="structural_partial_labelled_slots")


def interpret_bare_adjective_slot_label(record: dict[str, Any]) -> AdjectiveSlots | None:
    lemma = _value(record, "normaliserat_ord").casefold()
    raw_text = normalize_notation(_value(record, "text"))
    if not lemma or " " in lemma or not lemma.isalpha() or raw_text != "best.":
        return None
    return AdjectiveSlots(
        lemma=lemma,
        forms=(AdjectiveForm(lemma, "definite_or_plural"),),
        rule="structural_bare_slot_label",
    )


def interpret_full_labelled_adjective_slots(record: dict[str, Any]) -> AdjectiveSlots | None:
    """Interpret rich labelled sequences by state, not by whole-paradigm regex."""
    lemma = _value(record, "normaliserat_ord").casefold()
    raw_text = _value(record, "text")
    if not lemma or " " in lemma or not lemma.isalpha() or not raw_text:
        return None
    tokens = tokenize_notation(normalize_notation(raw_text))
    if tokens is None or "best." not in tokens or "pl." not in tokens:
        return None

    forms: list[AdjectiveForm] = [AdjectiveForm(lemma, "common_singular")]
    state = "positive"
    positive_count = 0
    best_count = 0
    post_plural_count = 0
    for token in tokens:
        lower = token.casefold()
        if token in {",", ";"}:
            continue
        if lower == "best.":
            state = "best"
            continue
        if lower == "pl.":
            state = "plural"
            continue
        operation = _single_operation(token)
        if operation is None:
            return None
        if state == "positive":
            if positive_count != 0:
                return None
            slot = "neuter_singular"
            positive_count += 1
        elif state == "best":
            if best_count == 0:
                slot = "masculine_definite"
            elif best_count == 1:
                slot = "definite_or_plural"
            else:
                return None
            best_count += 1
        elif state == "plural":
            if post_plural_count == 0:
                slot = "definite_or_plural"
            elif post_plural_count == 1:
                slot = "comparative"
            elif post_plural_count == 2:
                slot = "superlative"
            else:
                return None
            post_plural_count += 1
        else:
            return None
        value = _apply_positive_operation(lemma, operation, neuter=slot == "neuter_singular")
        if value is None:
            return None
        forms.append(AdjectiveForm(value, slot))

    if (positive_count, best_count, post_plural_count) != (1, 2, 3):
        return None
    return AdjectiveSlots(lemma=lemma, forms=_dedupe_forms(forms), rule="structural_full_labelled_slots")


def interpret_usage_restricted_adjective_slots(record: dict[str, Any]) -> AdjectiveSlots | None:
    lemma = _value(record, "normaliserat_ord").casefold()
    raw_text = _value(record, "text")
    if not lemma or " " in lemma or not lemma.isalpha() or not raw_text:
        return None
    tokens = tokenize_notation(normalize_notation(raw_text))
    if tokens is None:
        return None
    words = [token.casefold() for token in tokens if token not in {",", ";"}]
    forms: list[AdjectiveForm] = [AdjectiveForm(lemma, "common_singular")]
    restrictions: tuple[UsageRestriction, ...]
    form_token: str | None = None
    if words[:3] == ["n.", "sing.", "obest."] and len(words) in {4, 5}:
        if words[3] not in {"obrukl.", "undviks:"}:
            return None
        label = "uncommon" if words[3] == "obrukl." else "avoided"
        restrictions = (UsageRestriction("neuter_singular", label),)
        form_token = words[4] if len(words) == 5 else None
    elif len(words) == 3 and words[:2] == ["neutr.", "undviks:"]:
        restrictions = (UsageRestriction("neuter_singular", "avoided"),)
        form_token = words[2]
    elif len(words) == 7 and words[:6] == ["mest:", "oböjl.", "best.", "och:", "pl.", "ibl."]:
        form_token = words[6]
        restrictions = (UsageRestriction("paradigm", "mostly_uninflected"), UsageRestriction("definite_or_plural", "occasional"))
    else:
        return None
    if form_token is not None:
        operation = _single_operation(form_token)
        if operation is None:
            return None
        value = _apply_positive_operation(lemma, operation, neuter=False)
        if value is None:
            return None
        forms.append(AdjectiveForm(value, "definite_or_plural"))
        if len(restrictions) == 2 and restrictions[1].label == "occasional":
            restrictions = (restrictions[0], UsageRestriction("definite_or_plural", "occasional", (value,)))
    return AdjectiveSlots(lemma=lemma, forms=_dedupe_forms(forms), rule="structural_usage_restrictions", restrictions=restrictions)


def _common_from_neuter_for_e_plural(neuter: str) -> str | None:
    if not neuter.endswith("at"):
        return None
    return neuter[:-2] + "ad"


def _parallel_positive_implicit_slot(index: int, _last_slot: str | None, _operation: FormOperation) -> str | None:
    if index == 0:
        return "neuter_singular"
    if index == 1:
        return "definite_or_plural"
    return None


_ADJECTIVE_PARALLEL_POSITIVE_GRAMMAR = SlotGrammar(label_slots={}, implicit_slot=_parallel_positive_implicit_slot)


def interpret_parallel_positive_adjective_slots(record: dict[str, Any]) -> AdjectiveSlots | None:
    lemma = _value(record, "normaliserat_ord").casefold()
    raw_text = _value(record, "text")
    if not lemma or " " in lemma or not lemma.isalpha() or " _ " not in f" {raw_text} ":
        return None
    branches = interpret_slot_branches(raw_text, _ADJECTIVE_PARALLEL_POSITIVE_GRAMMAR)
    if branches is None or len(branches) < 2:
        return None
    prefix = _compound_prefix(record, lemma)
    forms: list[AdjectiveForm] = [AdjectiveForm(lemma, "common_singular")]
    for branch in branches:
        if len(branch.operations) != 2:
            return None
        neuter_item, plural_item = branch.operations
        if neuter_item.slot != "neuter_singular" or plural_item.slot != "definite_or_plural":
            return None
        neuter_operation = neuter_item.operation
        plural_operation = plural_item.operation
        if neuter_operation.kind in {FormOperationKind.APPEND, FormOperationKind.UNCHANGED} and plural_operation.kind is FormOperationKind.EXPLICIT:
            return None
        neuter = _apply_positive_operation(lemma, neuter_operation, neuter=True)
        if neuter is None and prefix and neuter_operation.kind is FormOperationKind.REPLACE_TAIL:
            neuter = prefix + neuter_operation.value
        if neuter is None:
            return None
        branch_common: str | None = None
        if plural_operation.kind is FormOperationKind.APPEND and plural_operation.value.casefold() == "e" and neuter_operation.kind in {FormOperationKind.EXPLICIT, FormOperationKind.REPLACE_TAIL}:
            branch_common = _common_from_neuter_for_e_plural(neuter)
            if branch_common is None:
                return None
        plural_base = branch_common or lemma
        definite = _apply_positive_operation(plural_base, plural_operation, neuter=False)
        if definite is None:
            return None
        if branch_common is not None:
            forms.append(AdjectiveForm(branch_common, "common_singular"))
        forms.extend((AdjectiveForm(neuter, "neuter_singular"), AdjectiveForm(definite, "definite_or_plural")))
    return AdjectiveSlots(lemma=lemma, forms=_dedupe_forms(forms), rule="structural_parallel_positive_branches")


def interpret_adjective_row(record: dict[str, Any]) -> AdjectiveSlots | None:
    return (
        interpret_unlabelled_positive_adjective_slots(record)
        or interpret_unlabelled_adjective_alternatives(record)
        or interpret_labelled_positive_adjective_slots(record)
        or interpret_labelled_comparison_adjective_slots(record)
        or interpret_unlabelled_comparison_alternatives(record)
        or interpret_partial_labelled_adjective_slots(record)
        or interpret_bare_adjective_slot_label(record)
        or interpret_full_labelled_adjective_slots(record)
        or interpret_usage_restricted_adjective_slots(record)
        or interpret_parallel_positive_adjective_slots(record)
        or interpret_simple_adjective_slots(record)
    )