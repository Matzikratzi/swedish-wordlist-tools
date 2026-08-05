from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Callable


@dataclass(frozen=True)
class NotationBranch:
    """One SAOL alternative branch after comments and whitespace are normalized."""

    text: str
    tokens: tuple[str, ...]


class FormOperationKind(str, Enum):
    """Primitive operations used by SAOL inflection notation."""

    UNCHANGED = "unchanged"
    APPEND = "append"
    REPLACE_TAIL = "replace_tail"
    EXPLICIT = "explicit"


@dataclass(frozen=True)
class FormOperation:
    """An ordklass-neutral interpretation of one form token.

    Examples:
    ``+`` becomes ``UNCHANGED``; ``+a`` becomes ``APPEND('a')``;
    ``-bundna`` becomes ``REPLACE_TAIL('bundna')``; and a fully written form
    such as ``bättre`` becomes ``EXPLICIT('bättre')``.
    """

    kind: FormOperationKind
    value: str = ""
    source: str = ""


_BRACKET_COMMENT = re.compile(r"\s*\[[^\]]*\]")
_FORM_WORD = re.compile(r"[a-zåäöéü]+", re.IGNORECASE)


def normalize_notation(text: str) -> str:
    """Remove non-form bracket comments and normalize separators/whitespace.

    SAOL uses bracketed material for pronunciation or morphophonemic comments,
    e.g. ``högt [hök>t]`` and ``perent [-en>t]``. Those comments describe a
    form but are never themselves playable word material.
    """

    text = _BRACKET_COMMENT.sub("", text)
    text = " ".join(text.split()).casefold()
    return text


def parse_form_operation(token: str) -> FormOperation | None:
    """Parse one lexical SAOL token into a primitive form operation.

    The function deliberately does not decide *which grammatical slot* the
    token belongs to. It also leaves ordklass-specific spelling changes to the
    caller. For example, adjective ``+t`` is represented as ``APPEND('t')``;
    the adjective layer may then realize ``glad`` as ``glatt``.
    """

    normalized = token.strip().casefold()
    if normalized == "+":
        return FormOperation(FormOperationKind.UNCHANGED, source=normalized)
    if normalized.startswith("+-"):
        value = normalized[2:]
        if _FORM_WORD.fullmatch(value):
            return FormOperation(FormOperationKind.APPEND, value, normalized)
        return None
    if normalized.startswith("+"):
        value = normalized[1:]
        if _FORM_WORD.fullmatch(value):
            return FormOperation(FormOperationKind.APPEND, value, normalized)
        return None
    if normalized.startswith("-"):
        value = normalized[1:]
        if _FORM_WORD.fullmatch(value):
            return FormOperation(FormOperationKind.REPLACE_TAIL, value, normalized)
        return None
    if _FORM_WORD.fullmatch(normalized):
        return FormOperation(FormOperationKind.EXPLICIT, normalized, normalized)
    return None


def _best_overlap_replacement(base: str, tail: str) -> tuple[str | None, int]:
    """Replace the suffix position sharing the longest prefix with ``tail``.

    This is a conservative fallback for rows without a usable lodstreck.  It
    chooses the position where the existing word ending and the replacement
    form agree for the greatest number of initial characters.  For example,
    ``barntillåten`` + ``tillåtet`` aligns at ``tillåte`` rather than at the
    final ``t`` and therefore yields ``barntillåtet``.
    """

    best_index = -1
    best_score = 0
    for index in range(len(base)):
        score = 0
        while (
            index + score < len(base)
            and score < len(tail)
            and base[index + score] == tail[score]
        ):
            score += 1
        if score > best_score:
            best_index = index
            best_score = score
    if best_index < 0:
        return None, 0
    return base[:best_index] + tail, best_score


def apply_form_operation(
    base: str,
    operation: FormOperation,
    *,
    append: Callable[[str, str], str | None] | None = None,
    replace_tail: Callable[[str, str], str | None] | None = None,
) -> str | None:
    """Apply a primitive operation, with optional ordklass-specific handlers."""

    if operation.kind is FormOperationKind.UNCHANGED:
        return base
    if operation.kind is FormOperationKind.EXPLICIT:
        return operation.value
    if operation.kind is FormOperationKind.APPEND:
        return append(base, operation.value) if append else base + operation.value
    if operation.kind is FormOperationKind.REPLACE_TAIL:
        handled = replace_tail(base, operation.value) if replace_tail else None
        overlap, score = _best_overlap_replacement(base, operation.value)
        return overlap if score >= 2 else handled
    return None


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
