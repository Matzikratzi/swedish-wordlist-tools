from __future__ import annotations

import re
from typing import Any

from .saol_notation import (
    FormOperationKind,
    assign_labeled_slots,
    split_alternative_branches,
    tokenize_notation,
)
from .saol_row_interpreter import interpret_noun_row

MECHANICALLY_VERIFIED_NOUN_NOTATIONS = frozenset(
    {
        "+en",
        "+et",
        "+n",
        "+t",
        "+en +er",
        "+en +ar",
        "+et +er",
        "+n +er",
        "+n +r",
        "+t +n",
        "+et; pl. +",
        "+en; pl. +",
        "+n; pl. +",
        "+t; pl. +",
    }
)

_EXPLICIT_PLURAL = re.compile(r"^\+(?:en|n|et|t)(?:\s*;\s*pl\.)?\s+-[^\s;,]+$")
_USED_IN_PLURAL = re.compile(r"^best\. \+; i: pl\. används: -[^\s;,]+$")
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


def _is_fully_relative_slot_notation(notation: str) -> bool:
    """Return true when every materialized slot form is relative to the lemma.

    ``el.`` and ``H`` are both alternative markers at this layer.  The shared
    notation parser assigns the operation after either marker to the same slot
    as the preceding form.  We therefore need no noun-specific H rule: if both
    alternatives are ordinary append/unchanged operations, SAOL has stated the
    complete alternative mechanically.
    """

    if "_" in notation:
        return False
    tokens = tokenize_notation(notation)
    if not tokens:
        return False
    assigned = assign_labeled_slots(
        tokens,
        singular_slot="sg_def",
        plural_slot="pl_indef",
        definite_plural_slot="pl_def",
    )
    if not assigned:
        return False
    return all(
        item.operation.kind in {FormOperationKind.UNCHANGED, FormOperationKind.APPEND}
        for item in assigned
    )


def _is_fully_relative_branch_notation(notation: str) -> bool:
    if "_" not in notation or "el." in notation.casefold() or re.search(r"(?:^|\s)H(?:\s|$)", notation):
        return False
    branches = split_alternative_branches(notation)
    if len(branches) < 2:
        return False
    for branch in branches:
        assigned = assign_labeled_slots(
            branch.tokens,
            singular_slot="sg_def",
            plural_slot="pl_indef",
            definite_plural_slot="pl_def",
        )
        if not assigned:
            return False
        if any(
            item.operation.kind not in {FormOperationKind.UNCHANGED, FormOperationKind.APPEND}
            for item in assigned
        ):
            return False
    return True


def is_mechanically_verified_noun_notation(row_or_notation: dict[str, Any] | str) -> bool:
    notation = normalized_notation(row_or_notation)
    if notation in MECHANICALLY_VERIFIED_NOUN_NOTATIONS:
        return True
    if _EXPLICIT_PLURAL.fullmatch(notation) or _USED_IN_PLURAL.fullmatch(notation):
        return True
    if _VARDAGLIG_REPLACEMENT.fullmatch(notation):
        return True
    if _LABELED_REPLACEMENT_PARADIGM.fullmatch(notation):
        return True
    if _TWO_REPLACEMENT_PARADIGM.fullmatch(notation):
        return True
    if _is_fully_relative_slot_notation(notation):
        return True
    return _is_fully_relative_branch_notation(notation)


def is_mechanically_verified_noun_row(row: dict[str, Any]) -> bool:
    if is_mechanically_verified_noun_notation(row):
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
