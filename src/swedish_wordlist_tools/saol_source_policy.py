from __future__ import annotations

import re
from typing import Any

from .inflect import normalise_pattern

SOURCE_TEXT_LIMIT = 50
_TRIMMED_LIMIT_TRAILING_MARKER_RE = re.compile(
    r"(?:^|\s)(?:best\.|pl\.|el\.|ibl\.|H)$",
    re.IGNORECASE,
)


def raw_inflection_text(record: dict[str, Any]) -> str:
    """Return the raw SAOL ``text`` carrier as stored in the export."""

    value = record.get("text")
    if value is None:
        value = record.get("notation")
    return "" if value is None else str(value)


def _looks_like_trimmed_limit_boundary(text: str) -> bool:
    """Detect a 50-character export cut whose final blank was stripped.

    Some exported values appear with 49 visible characters when character 50
    was a separating blank that disappeared during export/serialization.  We
    classify those conservatively only when the visible string ends in a SAOL
    structural marker that requires a following form, e.g. ``best.``.
    """

    return (
        len(text) == SOURCE_TEXT_LIMIT - 1
        and _TRIMMED_LIMIT_TRAILING_MARKER_RE.search(text) is not None
    )


def is_truncated_inflection_source(record: dict[str, Any]) -> bool:
    """Return true when SAOL ``text`` hits the known 50-character export cap.

    This includes the observed case where the 50th character was a separating
    blank and the stored/exported value therefore has only 49 visible
    characters.  The 49-character case is accepted only when the text ends in
    an incomplete structural marker, avoiding a blanket assumption that every
    ordinary 49-character value is truncated.

    Such rows may still contain useful completed notation before the final
    fragment, but they must not be mixed into the ordinary queue of rows whose
    complete source notation is available.
    """

    text = raw_inflection_text(record)
    return len(text) == SOURCE_TEXT_LIMIT or _looks_like_trimmed_limit_boundary(text)


def inflection_text(record: dict[str, Any]) -> str | None:
    """Return SAOL's primary inflection text, or ``None`` when it is absent.

    ``text`` is the authoritative inflection carrier whenever it is present.
    The formatted ``ordkl`` field must not be merged into or used to complete a
    non-empty ``text`` value; its presentation copy is frequently truncated.
    """

    return normalise_pattern(record.get("text"))


def may_use_ordkl_for_inflection(record: dict[str, Any]) -> bool:
    """Return true only when SAOL's primary inflection ``text`` is absent."""

    return inflection_text(record) is None
