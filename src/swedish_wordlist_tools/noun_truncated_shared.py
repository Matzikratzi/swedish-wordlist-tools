from __future__ import annotations

from typing import Any

from .saol_notation import split_alternative_branches
from .saol_row_interpreter import (
    InterpretedRow,
    KeyForm,
    _assign_labelled_noun_slots_shared,
    _assign_unlabelled_noun_atoms_shared,
    _branch_lemma_variant,
    _clean_notation_structure,
    _explicit_branch_bases,
    _is_uninflected_branch,
    apply_form_operation_to_noun,
)
from .saol_source_policy import inflection_text


def assign_truncated_noun_branch(record: dict[str, Any], tokens: tuple[str, ...]):
    """Return the longest safely interpretable shared prefix of a truncated branch.

    This is deliberately only a prefix recovery mechanism.  It never supplies a
    missing operation, slot, or ending.  Callers must already know that the source
    row is truncated; complete rows must use the ordinary shared grammar directly.
    """

    for end in range(len(tokens), 0, -1):
        prefix = tokens[:end]
        assigned = _assign_labelled_noun_slots_shared(prefix)
        if assigned is None:
            assigned = _assign_unlabelled_noun_atoms_shared(record, prefix)
        if assigned is not None:
            return assigned
    return None


def interpret_truncated_noun_row(record: dict[str, Any]) -> InterpretedRow | None:
    """Interpret only the evidenced shared prefix of a known-truncated NOUN row."""

    if str(record.get("upos") or "").upper() != "NOUN":
        return None
    lemma = str(record.get("normaliserat_ord") or "").strip()
    pattern = inflection_text(record)
    if not lemma or pattern is None:
        return None

    branches = split_alternative_branches(_clean_notation_structure(pattern))
    if not branches:
        return None
    branch_bases = _explicit_branch_bases(record, lemma, len(branches))

    key_forms: list[KeyForm] = [KeyForm("lemma", lemma, "lemma")]
    seen: set[tuple[str, str]] = {("lemma", lemma)}
    recovered_any = False

    for branch_index, branch in enumerate(branches):
        branch_base = branch_bases[branch_index]
        if branch_base.casefold() != lemma.casefold():
            marker = ("lemma", branch_base)
            if marker not in seen:
                seen.add(marker)
                key_forms.append(KeyForm("lemma", branch_base, "explicit_variant_branch"))

        if _is_uninflected_branch(branch.tokens):
            recovered_any = True
            continue

        lemma_variant = _branch_lemma_variant(branch_base, branch.tokens)
        if lemma_variant is not None:
            written_form, source = lemma_variant
            marker = ("lemma", written_form)
            if marker not in seen:
                seen.add(marker)
                key_forms.append(KeyForm("lemma", written_form, source))

        slot_operations = assign_truncated_noun_branch(record, branch.tokens)
        if slot_operations is None:
            # A truncated final branch can contain no complete form atom at all.
            # Keep forms recovered from earlier complete branches, if any.
            continue
        recovered_any = True
        for assigned in slot_operations:
            written_form = apply_form_operation_to_noun(record, branch_base, assigned.operation)
            if written_form is None:
                continue
            marker = (assigned.slot, written_form)
            if marker not in seen:
                seen.add(marker)
                key_forms.append(KeyForm(assigned.slot, written_form, assigned.token))

    if not recovered_any:
        return None
    return InterpretedRow(lemma, pattern, tuple(key_forms))
