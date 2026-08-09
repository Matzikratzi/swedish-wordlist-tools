from __future__ import annotations

import re
from typing import Any

# Conservative allow-list of simple SAOL noun paradigms whose completion is
# fully mechanical once the article notation has been parsed. SAOL licenses the
# slots; SAG supplies the ordinary inflectional completion (genitive and
# definite plural).
#
# Checked against Svenska Akademiens grammatik (SAG), vol. 2, noun number and
# definiteness inflection, with svenska.se used only for spot validation.
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

# A second mechanical family writes the plural stem/form explicitly instead of
# giving a productive suffix, e.g. ``+n -syror`` or ``+en -rötter``.  There is
# no lexical inference here: the plural is stated by SAOL.  The parser only has
# to apply the replacement and complete ordinary definite plural/genitive.
_EXPLICIT_PLURAL = re.compile(r"^\+(?:en|n|et|t) -[^\s;,]+$")

# SAOL also marks nouns whose ordinary article is singular but for which a
# particular plural is explicitly used, e.g. ``best. +; i: pl. används:
# -verkningar``.  Again the plural itself is lexical information from SAOL;
# only its ordinary inflectional completion is mechanical.
_USED_IN_PLURAL = re.compile(r"^best\. \+; i: pl\. används: -[^\s;,]+$")


def normalized_notation(row_or_notation: dict[str, Any] | str) -> str:
    if isinstance(row_or_notation, str):
        value = row_or_notation
    else:
        value = str(row_or_notation.get("notation") or "")
    return " ".join(value.strip().split())


def is_mechanically_verified_noun_notation(row_or_notation: dict[str, Any] | str) -> bool:
    """Return true only for audited SAOL noun notation families.

    Alternative branches (``el.``, ``_``), bracket operations and compound
    slot expressions are intentionally not accepted by the pattern rules.
    """
    notation = normalized_notation(row_or_notation)
    if notation in MECHANICALLY_VERIFIED_NOUN_NOTATIONS:
        return True
    return bool(_EXPLICIT_PLURAL.fullmatch(notation) or _USED_IN_PLURAL.fullmatch(notation))
