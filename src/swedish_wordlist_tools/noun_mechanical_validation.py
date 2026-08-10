from __future__ import annotations

import re
from typing import Any

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

# SAOL may state a lexical plural replacement either directly after the
# singular form or with an explicit ``pl.`` label. In both cases the lexical
# information comes wholly from SAOL; completion only adds ordinary definite
# plural and genitive mechanically.
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


def is_mechanically_verified_noun_notation(row_or_notation: dict[str, Any] | str) -> bool:
    """Return true only for audited SAOL noun notation families.

    Alternative branches (``el.``, ``_``), bracket operations and compound
    slot expressions are not accepted here merely from their spelling. Branch
    rows can instead be verified structurally by
    ``is_mechanically_verified_noun_row`` after materialization has proved the
    separate variant paradigms.
    """
    notation = normalized_notation(row_or_notation)
    if notation in MECHANICALLY_VERIFIED_NOUN_NOTATIONS:
        return True
    return bool(_EXPLICIT_PLURAL.fullmatch(notation) or _USED_IN_PLURAL.fullmatch(notation))


def _has_materialized_alternative_branches(row: dict[str, Any]) -> bool:
    """Return true when an ``_`` notation has separately materialized variants.

    The validation artifact records one entry per variant lemma. Requiring at
    least two non-empty variant paradigms means we do not infer branch bases
    merely from the underscore syntax: the branch binding has already been
    established structurally during SAOL generation (for example
    ``bankväsen`` / ``bankväsende``).
    """

    notation = normalized_notation(row)
    if " _ " not in f" {notation} ":
        return False
    variants = row.get("variant_validation")
    if not isinstance(variants, list) or len(variants) < 2:
        return False
    lemmas: set[str] = set()
    for variant in variants:
        if not isinstance(variant, dict):
            return False
        lemma = str(variant.get("lemma") or "").strip().casefold()
        forms = variant.get("generated_forms")
        if not lemma or not isinstance(forms, list) or not forms:
            return False
        lemmas.add(lemma)
    return len(lemmas) >= 2


def is_mechanically_verified_noun_row(row: dict[str, Any]) -> bool:
    if is_mechanically_verified_noun_notation(row):
        return True

    if _has_materialized_alternative_branches(row):
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
