from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class NotationBranch:
    """One SAOL alternative branch after comments and whitespace are normalized."""

    text: str
    tokens: tuple[str, ...]


_BRACKET_COMMENT = re.compile(r"\s*\[[^\]]*\]")


def normalize_notation(text: str) -> str:
    """Remove non-form bracket comments and normalize separators/whitespace.

    SAOL uses bracketed material for pronunciation or morphophonemic comments,
    e.g. ``högt [hök>t]`` and ``perent [-en>t]``. Those comments describe a
    form but are never themselves playable word material.
    """

    text = _BRACKET_COMMENT.sub("", text)
    text = " ".join(text.split()).casefold()
    return text


def split_alternative_branches(text: str) -> tuple[NotationBranch, ...]:
    """Split top-level SAOL alternatives marked by ``_``.

    The returned tokens retain punctuation-bearing labels (``komp.``, ``pl.``)
    so an ordklass-specific slot mapper can interpret them.
    """

    normalized = normalize_notation(text)
    branches: list[NotationBranch] = []
    for branch in normalized.split(" _ "):
        branch = branch.strip()
        if not branch:
            continue
        branches.append(NotationBranch(branch, tuple(branch.split())))
    return tuple(branches)


def split_forms(text: str) -> tuple[str, ...]:
    """Return lexical/operation tokens while discarding common separators.

    This is intentionally ordklass-neutral. Labels are preserved; only pure
    separators are removed. ``el.`` and ``H`` both mean alternative form.
    """

    normalized = normalize_notation(text)
    normalized = normalized.replace(",", " ").replace(";", " ").replace(":", " ")
    return tuple(
        token
        for token in normalized.split()
        if token not in {"el.", "h", "_", "och"}
    )
