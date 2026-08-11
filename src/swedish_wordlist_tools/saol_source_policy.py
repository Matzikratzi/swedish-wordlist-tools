from __future__ import annotations

from typing import Any

from .inflect import normalise_pattern

SOURCE_TEXT_LIMIT = 50


def raw_inflection_text(record: dict[str, Any]) -> str:
    """Return the raw SAOL ``text`` carrier as stored in the export."""

    value = record.get("text")
    if value is None:
        value = record.get("notation")
    return "" if value is None else str(value)


def is_truncated_inflection_source(record: dict[str, Any]) -> bool:
    """Return true when SAOL ``text`` may be incomplete at the export limit.

    The export cap is 50 characters, but trailing whitespace may disappear from
    the stored value. Therefore both 49- and 50-character strings are treated as
    potentially incomplete source rows.

    Their safety differs:

    * At 50 characters, the final visible token may itself be cut and must not be
      trusted. The notation layer therefore drops that final token before
      interpretation.
    * At 49 characters, the final visible token is complete and may be used, but
      the paradigm must still be considered open: more notation may have existed
      after an exported trailing blank.

    Shorter rows are treated as complete unless another source-level rule says
    otherwise.
    """

    text = raw_inflection_text(record)
    return len(text) in {SOURCE_TEXT_LIMIT - 1, SOURCE_TEXT_LIMIT}


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
