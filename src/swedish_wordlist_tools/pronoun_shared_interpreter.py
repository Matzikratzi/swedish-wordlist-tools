from __future__ import annotations

from typing import Any, Mapping

from .lexeme_slots import LexemeSlots, SlotForm, build_lexeme_slots
from .saol_notation import FormOperationKind, SlotOperation, apply_form_operation
from .saol_slot_interpreter import (
    SlotGrammar,
    interpret_single_slot_sequence,
    interpret_slot_branches,
)
from .saol_source_policy import is_truncated_inflection_source


def _implicit_pronoun_slot(index: int, last_slot: str | None, _operation) -> str | None:
    if index == 0:
        return "neuter_singular"
    if index == 1:
        return "plural"
    if last_slot == "masculine_definite":
        return "definite_or_plural"
    return None


_PRONOUN_GRAMMAR = SlotGrammar(
    label_slots={
        "n.": "neuter_singular",
        "pl.": "plural",
        "gen.": "genitive",
        "mask.": "masculine_definite",
        "best.": "masculine_definite",
        "objektsform:": "object",
        "superl.": "superlative",
    },
    implicit_slot=_implicit_pronoun_slot,
    transparent_markers=frozenset({
        "i:", "som:", "används:", "anv.", "sing.", "substantivisk:",
        "uttalat:", "och:", "också:", "skrivet:", "sällan:",
        "högt.", "vard.",
    }),
    allow_generic_editorial_markers=False,
)


def _primary_text(record: Mapping[str, Any]) -> str:
    """Return SAOL's primary PRON inflection carrier only.

    A missing ``text`` field means that this record has no primary inflection
    notation. Do not fall back to presentation/derived notation here; doing so
    would make lemma-only records look like inflected records and differs from
    the source policy used for the other word classes.
    """

    value = record.get("text")
    if value is None or str(value) == "(null)":
        return ""
    return str(value).strip()


def _safe_text(record: Mapping[str, Any]) -> str:
    text = _primary_text(record)
    if not text:
        return ""
    if not is_truncated_inflection_source(dict(record)):
        return text
    # saol_notation itself drops an unsafe final token at exactly 50 chars.
    # A 49-char row keeps its final complete token but remains an open paradigm.
    return text


def _realize_operations(
    lemma: str,
    operations: tuple[SlotOperation, ...],
) -> list[SlotForm] | None:
    forms: list[SlotForm] = []
    for item in operations:
        operation = item.operation
        # Until PRON lodstreck semantics are audited, never guess a '-' form.
        if operation.kind is FormOperationKind.REPLACE_TAIL:
            return None
        written = apply_form_operation(lemma, operation)
        if written is None:
            return None
        forms.append(
            SlotForm(
                item.slot,
                written.casefold(),
                item.token,
                "shared_pronoun",
                item.alternative_relation or "",
            )
        )
    return forms


def interpret_pronoun_row(record: Mapping[str, Any]) -> LexemeSlots | None:
    if str(record.get("upos") or "").upper() != "PRON":
        return None
    lemma = str(record.get("normaliserat_ord") or "").strip().casefold()
    text = _safe_text(record)
    if not lemma or not text:
        return None

    # Bare labels are structural evidence that the unchanged lemma occupies
    # that slot. Handle the few genuinely bare PRON paradigms explicitly by
    # grammar, not by lemma spelling.
    normalized = " ".join(text.casefold().split())
    if normalized == "pl.":
        return build_lexeme_slots(
            lemma=lemma,
            upos="PRON",
            notation=text,
            forms=(SlotForm("plural", lemma, "pl.", "shared_pronoun"),),
            metadata={"rule": "shared_bare_plural"},
        )
    if normalized == "n. sing.":
        return build_lexeme_slots(
            lemma=lemma,
            upos="PRON",
            notation=text,
            forms=(SlotForm("neuter_singular", lemma, "n. sing.", "shared_pronoun"),),
            metadata={"rule": "shared_bare_neuter_singular"},
        )

    assigned = interpret_single_slot_sequence(text, _PRONOUN_GRAMMAR)
    rule = "shared_pronoun_slots"
    operation_groups: list[tuple[SlotOperation, ...]] = []
    if assigned is not None:
        operation_groups.append(assigned)
    else:
        branches = interpret_slot_branches(text, _PRONOUN_GRAMMAR)
        if branches is None:
            return None
        operation_groups.extend(branch.operations for branch in branches)
        rule = "shared_pronoun_branches"

    forms: list[SlotForm] = []
    for operations in operation_groups:
        realized = _realize_operations(lemma, operations)
        if realized is None:
            return None
        forms.extend(realized)

    return build_lexeme_slots(
        lemma=lemma,
        upos="PRON",
        notation=text,
        forms=forms,
        metadata={
            "rule": rule,
            "truncated": "yes" if is_truncated_inflection_source(dict(record)) else "no",
        },
    )
