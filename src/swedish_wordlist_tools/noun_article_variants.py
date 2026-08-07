from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

_SUP_RE = re.compile(r"<sup\b[^>]*>.*?</sup>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]*>")
_BRANCH_RE = re.compile(r"\s+_\s+")


@dataclass(frozen=True)
class NounArticleVariant:
    lemma: str
    notation: str


@dataclass(frozen=True)
class NounArticleVariantPlan:
    normalised_lemma: str
    variants: tuple[NounArticleVariant, ...]
    mode: str


def clean_printed_word(value: Any) -> str:
    """Return the lexical spelling from SAOL's printed ``ord`` field.

    Middle dots and vertical bars are layout/morpheme-boundary markup, not part
    of the playable spelling.
    """

    text = unicodedata.normalize("NFKC", str(value or ""))
    text = _SUP_RE.sub("", text)
    text = _TAG_RE.sub("", text)
    text = text.replace("\u00ad", "").replace("·", "").replace("|", "")
    return re.sub(r"\s+", " ", text).strip()


def split_notation_branches(value: Any) -> tuple[str, ...]:
    text = str(value or "").strip()
    if not text:
        return ("",)
    return tuple(part.strip() for part in _BRANCH_RE.split(text) if part.strip())


def _same_article_metadata(rows: list[dict[str, Any]]) -> bool:
    if not rows:
        return False
    return (
        len({str(row.get("normaliserat_ord") or "").casefold() for row in rows}) == 1
        and len({str(row.get("text") or "").strip() for row in rows}) == 1
        and len({str(row.get("stycke") or "").strip() for row in rows}) == 1
    )


def _ordered_bases(rows: list[dict[str, Any]], normalised_lemma: str) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for row in rows:
        base = clean_printed_word(row.get("ord"))
        folded = base.casefold()
        if base and folded not in seen:
            seen.add(folded)
            ordered.append(base)

    matching = [base for base in ordered if base.casefold() == normalised_lemma.casefold()]
    if len(matching) != 1:
        return ()
    main = matching[0]
    return (main, *(base for base in ordered if base.casefold() != main.casefold()))


def plan_noun_article_variants(rows: list[dict[str, Any]]) -> NounArticleVariantPlan | None:
    """Resolve unambiguous SAOL article variants to lemma/notation pairs.

    The raw SAOL export duplicates one printed article into several rows when
    ``ord`` contains alternative lexical headwords.  The rows retain the same
    ``normaliserat_ord``, ``text`` and ``stycke``.  Two unambiguous layouts are
    supported:

    * several ``ord`` variants and one notation branch: every lemma receives
      the same paradigm (for example ``abrovink`` / ``abrovinsch``);
    * the same number of ``ord`` variants and underscore-separated notation
      branches: branch 1 belongs to the normalised/main lemma and subsequent
      branches belong to the subsequent alternative ``ord`` variants (for
      example ``bankväsen`` / ``bankväsende``).

    Any other cardinality is deliberately left unresolved.
    """

    if len(rows) < 2 or not _same_article_metadata(rows):
        return None

    normalised = str(rows[0].get("normaliserat_ord") or "").strip()
    if not normalised:
        return None
    bases = _ordered_bases(rows, normalised)
    if len(bases) < 2:
        return None

    branches = split_notation_branches(rows[0].get("text"))
    if len(branches) == 1:
        variants = tuple(NounArticleVariant(base, branches[0]) for base in bases)
        return NounArticleVariantPlan(normalised, variants, "shared_notation")

    if len(branches) == len(bases):
        variants = tuple(
            NounArticleVariant(base, branch)
            for base, branch in zip(bases, branches)
        )
        return NounArticleVariantPlan(normalised, variants, "parallel_branches")

    return None
