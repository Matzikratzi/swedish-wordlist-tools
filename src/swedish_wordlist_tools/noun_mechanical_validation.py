from __future__ import annotations

import re
from typing import Any

from .saol_notation import FormOperationKind, assign_labeled_slots, split_alternative_branches
from .saol_row_interpreter import interpret_noun_row

MECHANICALLY_VERIFIED_NOUN_NOTATIONS = frozenset(
    {
        # Singular-only articles. SAOL explicitly licenses the singular slot;
        # ordinary genitive completion is mechanical. A broader or competing
        # SALDO paradigm is diagnostic, not evidence against the SAOL forms.
        "+en",
        "+et",
        "+n",
        "+t",
        # Regular productive paradigms.
        "+en +er",
        "+en +ar",
        "+et +er",
        "+n +er",
        "+n +r",
        "+t +n",
        # Simple zero-plural paradigms.
        "+et; pl. +",
        "+en; pl. +",
        "+n; pl. +",
        "+t; pl. +",
    }
)

_EXPLICIT_PLURAL = re.compile(
    r"^\+(?:en|n|et|t)(?:\s*;\s*pl\.)?\s+-[^\s;,]+$"
)
_USED_IN_PLURAL = re.compile(r"^best\. \+; i: pl\. används: -[^\s;,]+$")
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


def _is_fully_relative_branch_notation(notation: str) -> bool:
    """Verify ``_`` alternatives whose grammatical information is all relative.

    ``_`` itself merely separates complete SAOL paradigm branches.  Such a row
    is mechanically safe when every branch can be assigned to noun slots and
    every actual form operation is either unchanged or an append operation.
    There is then no lexical guess: SAOL states every branch, while the noun
    interpreter supplies the branch base (including an hv-bound alternative
    spelling where the article has one).

    Explicit words, tail replacements, ``el.`` alternatives and H-marked forms
    remain outside this family and stay diagnostic.
    """

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
