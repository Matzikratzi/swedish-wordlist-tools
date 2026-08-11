from __future__ import annotations

from typing import Any

from .lexeme_slots import LexemeSlots, SlotForm, build_lexeme_slots
from .saol_notation import FormOperation, FormOperationKind, apply_form_operation, split_alternative_branches
from .saol_source_policy import inflection_text, is_truncated_inflection_source
from .verb_shared_slot_interpreter import (
    interpret_basic_verb_sequence,
    interpret_verb_sequence,
    is_structurally_uninflected_verb,
)
from .verb_truncated_shared import assign_truncated_verb_branch


def _playable_lemma(record: dict[str, Any]) -> str | None:
    if str(record.get("upos") or "").upper() != "VERB":
        return None
    lemma = str(record.get("normaliserat_ord") or "").strip()
    if not lemma or " " in lemma or lemma.startswith("-") or lemma.endswith("-"):
        return None
    return lemma


def _common_prefix_length(left: str, right: str) -> int:
    count = 0
    for a, b in zip(left.casefold(), right.casefold()):
        if a != b:
            break
        count += 1
    return count


def _replace_verb_final_component(lemma: str, replacement: str) -> str | None:
    """Realize SAOL ``-tail`` using the old spelling semantics, not old parsing.

    Verb replacements occasionally share only one initial letter with the
    replaced final component (``ange`` + ``-gav`` -> ``angav``), so the generic
    two-letter overlap threshold is deliberately relaxed here.  For multiword
    lemmas only the first word would be affected, but such lemmas are excluded
    from this direct playable path before realization.
    """

    best_start: int | None = None
    best_shared = 0
    for start in range(len(lemma)):
        candidate = lemma[start:]
        shared = _common_prefix_length(candidate, replacement)
        if shared > best_shared and len(candidate) >= 3:
            best_start = start
            best_shared = shared
    if best_start is None or best_shared < 1:
        return None
    return lemma[:best_start] + replacement


def realize_verb_operation(lemma: str, operation: FormOperation) -> str | None:
    """Apply one already parsed SAOL operation to a verb lemma."""

    return apply_form_operation(
        lemma,
        operation,
        replace_tail=_replace_verb_final_component,
    )


def _metadata(record: dict[str, Any], *, truncated: bool) -> dict[str, str]:
    return {
        "record_id": str(record.get("id") or record.get("subnr") or ""),
        "homonym_number": str(record.get("homonr") or ""),
        "stycke": str(record.get("stycke") or ""),
        "ordkl": str(record.get("ordkl") or ""),
        "shared_verb_slots": "true",
        "source_truncated": "true" if truncated else "false",
    }


def interpret_shared_playable_verb_slots(record: dict[str, Any]) -> LexemeSlots | None:
    """Build playable verb slots directly from the shared SAOL grammar.

    Complete rows use the ordinary shared interpreter.  Known 49/50-character
    rows use only the longest safely interpretable visible prefix.  No missing
    tense, participle, imperative, passive or other form is inferred here.
    """

    lemma = _playable_lemma(record)
    if lemma is None:
        return None

    pattern = inflection_text(record)
    truncated = is_truncated_inflection_source(record)
    if pattern is None:
        return build_lexeme_slots(
            lemma=lemma,
            upos="VERB",
            notation="",
            forms=(SlotForm("infinitive", lemma, "lemma", "shared_verb", "lemma"),),
            metadata=_metadata(record, truncated=False),
        )

    if is_structurally_uninflected_verb(pattern):
        return build_lexeme_slots(
            lemma=lemma,
            upos="VERB",
            notation=pattern,
            forms=(SlotForm("infinitive", lemma, "lemma", "shared_verb", "lemma"),),
            metadata=_metadata(record, truncated=truncated),
        )

    branches = split_alternative_branches(pattern)
    if not branches:
        return None

    forms: list[SlotForm] = [
        SlotForm("infinitive", lemma, "lemma", "shared_verb", "lemma")
    ]
    for branch in branches:
        if truncated:
            assigned = assign_truncated_verb_branch(branch.tokens)
        else:
            assigned = interpret_basic_verb_sequence(branch.text)
            if assigned is None:
                assigned = interpret_verb_sequence(branch.text)
        if assigned is None:
            return None
        for item in assigned:
            written = realize_verb_operation(lemma, item.operation)
            if written is None:
                return None
            detail = item.alternative_relation or item.alternative_marker or ""
            forms.append(
                SlotForm(
                    item.slot,
                    written,
                    item.token,
                    "shared_verb",
                    detail,
                )
            )

    return build_lexeme_slots(
        lemma=lemma,
        upos="VERB",
        notation=pattern,
        forms=forms,
        metadata=_metadata(record, truncated=truncated),
    )
