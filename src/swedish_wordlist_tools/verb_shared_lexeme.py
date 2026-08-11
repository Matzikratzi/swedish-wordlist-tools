from __future__ import annotations

from typing import Any

from .lexeme_slots import LexemeSlots, SlotForm, build_lexeme_slots
from .saol_notation import FormOperation, apply_form_operation, split_alternative_branches
from .saol_row_interpreter import compound_parts
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


def _join_compound_boundary(prefix: str, head: str) -> str:
    """Join SAOL compound parts using ordinary Swedish triple-consonant spelling."""

    if (
        len(prefix) >= 2
        and head
        and prefix[-1].casefold() == prefix[-2].casefold() == head[0].casefold()
    ):
        return prefix[:-1] + head
    return prefix + head


def _replace_verb_final_component(
    record: dict[str, Any], lemma: str, replacement: str
) -> str | None:
    """Realize SAOL ``-tail`` from the lexeme's explicit lodstreck structure.

    The divis replaces the part to the right of the final lodstreck.  This is
    the same structural rule already used by noun/adjective realization; no
    spelling-overlap heuristic is used for verbs.
    """

    parts = compound_parts(record, lemma)
    if parts is None:
        return None
    prefix, _head = parts
    return _join_compound_boundary(prefix, replacement)


def realize_verb_operation(
    record: dict[str, Any], lemma: str, operation: FormOperation
) -> str | None:
    """Apply one already parsed SAOL operation to a verb lemma."""

    return apply_form_operation(
        lemma,
        operation,
        replace_tail=lambda base, replacement: _replace_verb_final_component(
            record, base, replacement
        ),
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
            written = realize_verb_operation(record, lemma, item.operation)
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
