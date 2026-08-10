from __future__ import annotations

import re
from typing import Any

from .saol_notation import (
    FormOperationKind,
    SlotOperation,
    assign_notation_branches,
    is_direct_form_operation,
    parse_form_operations,
    split_alternative_branches,
)
from .saol_row_interpreter import interpret_noun_row

# Replacement operations still need source-aware application to a base spelling.
# These few historical forms remain here until REPLACE_TAIL has the same fully
# structural carrier model as direct operations. Ordinary +/explicit forms no
# longer need whole-notation allowlists.
_EXPLICIT_PLURAL_REPLACEMENT = re.compile(r"^\+(?:en|n|et|t)(?:\s*;\s*pl\.)?\s+-[^\s;,]+$")
_USED_IN_PLURAL_REPLACEMENT = re.compile(r"^best\. \+; i: pl\. används: -[^\s;,]+$")
_VARDAGLIG_REPLACEMENT = re.compile(
    r"^\+(?:en|et|n|t)\s+el\.\s+vard\.\s+-[^\s;,]+;\s*pl\.\s+\+[^\s;,_]+$",
    re.IGNORECASE,
)
_LABELED_REPLACEMENT_PARADIGM = re.compile(
    r"^-[^\s;,]+;\s*pl\.\s+\+,\s*best\.\s*pl\.\s+-[^\s;,]+$",
    re.IGNORECASE,
)
_TWO_REPLACEMENT_PARADIGM = re.compile(r"^-[^\s;,]+\s+-[^\s;,]+$")
_NULL_NOTATIONS = frozenset({"", "(null)", "null"})


def normalized_notation(row_or_notation: dict[str, Any] | str) -> str:
    if isinstance(row_or_notation, str):
        value = row_or_notation
    else:
        value = str(row_or_notation.get("notation") or "")
    return " ".join(value.strip().split())


def is_null_noun_notation(value: object) -> bool:
    if value is None:
        return True
    return str(value).strip().casefold() in _NULL_NOTATIONS


def _without_uninflected_branches(notation: str) -> tuple[str, bool]:
    """Remove branch-level ``oböjl.`` markers before slot verification."""

    branches = [part.strip() for part in re.split(r"\s+_\s+", notation) if part.strip()]
    if not branches:
        return notation, False
    kept = [part for part in branches if part.casefold() != "oböjl."]
    saw_uninflected = len(kept) != len(branches)
    return " _ ".join(kept), saw_uninflected


def _parsed_noun_branches(notation: str):
    ordinary, saw_uninflected = _without_uninflected_branches(notation)
    if not ordinary:
        return () if saw_uninflected else None
    return assign_notation_branches(
        ordinary,
        singular_slot="sg_def",
        plural_slot="pl_indef",
        definite_plural_slot="pl_def",
    )


def _is_direct_or_marker_licensed(item: SlotOperation) -> bool:
    """Whether this independent token is mechanically licensed by SAOL."""

    if is_direct_form_operation(item.operation):
        return True
    return (
        item.operation.kind is FormOperationKind.REPLACE_TAIL
        and item.alternative_marker == "ibl."
    )


def _is_explicit_only_notation(notation: str) -> bool:
    """Accept a noun inflection carrier made solely of fully written forms."""

    branches = split_alternative_branches(notation)
    if not branches:
        return False
    for branch in branches:
        if not branch.tokens:
            return False
        for token in branch.tokens:
            operations = parse_form_operations(token)
            if not operations or any(
                operation.kind is not FormOperationKind.EXPLICIT
                for operation in operations
            ):
                return False
    return True


def _is_directly_materialized_notation(notation: str) -> bool:
    """True when every independent form token/branch is mechanically licensed."""

    ordinary, saw_uninflected = _without_uninflected_branches(notation)
    if not ordinary:
        return saw_uninflected
    branches = assign_notation_branches(
        ordinary,
        singular_slot="sg_def",
        plural_slot="pl_indef",
        definite_plural_slot="pl_def",
    )
    if not branches:
        # A whole notation can fail common slot assignment merely because one
        # ``_`` branch consists only of explicit words. Verify each branch on
        # its own before falling back to the explicit-only carrier rule. This
        # keeps ``+n +ar _ bh:n bh:ar`` structural: the relative and explicit
        # branches are independent and neither depends on the other.
        raw_branches = split_alternative_branches(ordinary)
        if len(raw_branches) > 1:
            return all(_is_directly_materialized_notation(branch.text) for branch in raw_branches)
        return _is_explicit_only_notation(ordinary)
    return all(
        _is_direct_or_marker_licensed(item)
        for branch in branches
        for item in branch.operations
    )


def _artifact_materializes_replacements(row: dict[str, Any]) -> bool:
    """Trust REPLACE_TAIL only after the noun generator applied it successfully."""

    if str(row.get("generator") or "") != "canonical_artifact":
        return False
    branches = _parsed_noun_branches(normalized_notation(row))
    if branches is None:
        return False

    saw_replacement = False
    for branch in branches:
        for item in branch.operations:
            if item.operation.kind is FormOperationKind.REPLACE_TAIL:
                saw_replacement = True
            elif not is_direct_form_operation(item.operation):
                return False
    return saw_replacement


def is_mechanically_verified_noun_notation(row_or_notation: dict[str, Any] | str) -> bool:
    notation = normalized_notation(row_or_notation)
    if _is_directly_materialized_notation(notation):
        return True

    # Transitional source-aware REPLACE_TAIL cases. Everything else above is
    # already reduced to independent slot/branch operations rather than
    # paradigm regexes.
    return bool(
        _EXPLICIT_PLURAL_REPLACEMENT.fullmatch(notation)
        or _USED_IN_PLURAL_REPLACEMENT.fullmatch(notation)
        or _VARDAGLIG_REPLACEMENT.fullmatch(notation)
        or _LABELED_REPLACEMENT_PARADIGM.fullmatch(notation)
        or _TWO_REPLACEMENT_PARADIGM.fullmatch(notation)
    )


def is_mechanically_verified_noun_row(row: dict[str, Any]) -> bool:
    if is_mechanically_verified_noun_notation(row):
        return True
    if _artifact_materializes_replacements(row):
        return True
    if not is_null_noun_notation(row.get("notation")):
        return False

    interpreted = interpret_noun_row(
        {
            "upos": "NOUN",
            "normaliserat_ord": str(row.get("lemma") or ""),
            "ordkl": str(row.get("ordkl") or ""),
            "text": None,
        }
    )
    return interpreted is not None and interpreted.pattern.startswith("(ordkl:")
