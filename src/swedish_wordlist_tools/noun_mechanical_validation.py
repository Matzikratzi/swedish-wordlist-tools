from __future__ import annotations

from typing import Any

# Conservative allow-list of simple SAOL noun paradigms whose completion is
# fully mechanical once the article notation has been parsed. SAOL licenses the
# slots; SAG supplies the ordinary inflectional completion (genitive and
# definite plural). Alternative/branching notations are deliberately excluded.
#
# Checked against Svenska Akademiens grammatik (SAG), vol. 2, noun number and
# definiteness inflection, and spot-checked against SAOL on svenska.se.
MECHANICALLY_VERIFIED_NOUN_NOTATIONS = frozenset(
    {
        # Regular productive plural paradigms.
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


def normalized_notation(row_or_notation: dict[str, Any] | str) -> str:
    if isinstance(row_or_notation, str):
        value = row_or_notation
    else:
        value = str(row_or_notation.get("notation") or "")
    return " ".join(value.strip().split())


def is_mechanically_verified_noun_notation(row_or_notation: dict[str, Any] | str) -> bool:
    """Return true only for audited, non-branching SAOL noun notations."""
    return normalized_notation(row_or_notation) in MECHANICALLY_VERIFIED_NOUN_NOTATIONS
