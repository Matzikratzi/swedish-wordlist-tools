from __future__ import annotations

from typing import Any

from .inflect import normalise_pattern


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
