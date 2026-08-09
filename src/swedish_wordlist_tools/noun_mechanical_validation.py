from __future__ import annotations

import re
from typing import Any

from .saol_row_interpreter import interpret_noun_row
from .saol_source_policy import is_truncated_inflection_source

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
# giving a productive suffix, e.g. ``+n -syror`` or ``+en -rötter``. There is
# no lexical inference here: the plural is stated by SAOL. The parser only has
# to apply the replacement and complete ordinary definite plural/genitive.
_EXPLICIT_PLURAL = re.compile(r"^\+(?:en|n|et|t) -[^\s;,]+$")

# SAOL also marks nouns whose ordinary article is singular but for which a
# particular plural is explicitly used, e.g. ``best. +; i: pl. används:
# -verkningar``. Again the plural itself is lexical information from SAOL;
# only its ordinary inflectional completion is mechanical.
_USED_IN_PLURAL = re.compile(r"^best\. \+; i: pl\. används: -[^\s;,]+$")

_NULL_NOTATIONS = frozenset({"", "(null)", "null"})

# Structured alternatives are a separate safe family. They contain explicit
# SAOL alternative syntax (``el.`` or ``_``) and/or bracketed orthographic
# variants. We only accept them at row level after the ordinary noun interpreter
# has successfully parsed the complete source notation. This deliberately does
# *not* turn bare ``+et``, ``+en`` or ``+n`` into verified rows: those remain
# useful diagnostics for article scope/genus disagreements with SALDO.
_STRUCTURED_ALTERNATIVE_MARKER = re.compile(r"(?:\bel\.|\s_\s|\[[^\]]+\])", re.IGNORECASE)


def normalized_notation(row_or_notation: dict[str, Any] | str) -> str:
    if isinstance(row_or_notation, str):
        value = row_or_notation
    else:
        value = str(row_or_notation.get("notation") or "")
    return " ".join(value.strip().split())


def is_null_noun_notation(value: object) -> bool:
    """Return true for the representations used for missing SAOL ``text``."""

    if value is None:
        return True
    return str(value).strip().casefold() in _NULL_NOTATIONS


def is_mechanically_verified_noun_notation(row_or_notation: dict[str, Any] | str) -> bool:
    """Return true only for audited simple SAOL noun notation families.

    More structured alternatives are verified at row level, where the common
    SAOL interpreter can prove that the complete notation is actually parseable
    for the concrete lemma.
    """
    notation = normalized_notation(row_or_notation)
    if notation in MECHANICALLY_VERIFIED_NOUN_NOTATIONS:
        return True
    return bool(_EXPLICIT_PLURAL.fullmatch(notation) or _USED_IN_PLURAL.fullmatch(notation))


def _is_structured_alternative_row(row: dict[str, Any]) -> bool:
    notation = normalized_notation(row)
    if not notation or is_null_noun_notation(notation):
        return False
    if is_truncated_inflection_source(row):
        return False
    if _STRUCTURED_ALTERNATIVE_MARKER.search(notation) is None:
        return False

    # Colons introduce explanatory/usage prose in many SAOL rows (``i:``,
    # ``som:``, etc.). Keep those outside this broad mechanical family for now.
    # Colon-inflected abbreviation paradigms are handled separately elsewhere.
    if ":" in notation:
        return False

    interpreted = interpret_noun_row(
        {
            "upos": "NOUN",
            "normaliserat_ord": str(row.get("lemma") or ""),
            "stycke": str(row.get("stycke") or ""),
            "ordkl": str(row.get("ordkl") or ""),
            "text": notation,
        }
    )
    return interpreted is not None


def is_mechanically_verified_noun_row(row: dict[str, Any]) -> bool:
    """Verify a noun row from text notation or an ``ordkl`` fallback carrier.

    Besides the small audited simple families, complete structured alternative
    paradigms are accepted when the common noun interpreter parses them without
    inference. Thus ``el.``, ``_`` and bracket variants are treated as SAOL
    syntax rather than as hundreds of notation-specific exceptions.
    """

    if is_mechanically_verified_noun_notation(row):
        return True
    if _is_structured_alternative_row(row):
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
