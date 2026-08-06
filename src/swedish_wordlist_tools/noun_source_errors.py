from __future__ import annotations

from typing import Any


_KNOWN_LEMMA_ONLY_ROWS = {
    (
        "bygelbehå",
        "+n +ar _ -bh:n -bh:ar",
        "bygel|behå",
    ): "SAOL14 source issue: bygelbehå/bh replacement mismatch",
    (
        "sportbehå",
        "+n +ar _ -bh:n -bh:ar",
        "sport|behå",
    ): "SAOL14 source issue: sportbehå/bh replacement mismatch",
}


def _clean_stycke(value: Any) -> str:
    return str(value or "").replace("·", "").strip().casefold()


def noun_lemma_only_source_error(record: dict[str, Any]) -> str | None:
    """Return a source-error reason when only the noun lemma is trustworthy.

    Literal ``<k>`` markup in the exported ``text`` field is always an error.
    Other known source issues are matched by the complete source signature so
    an unrelated row with the same lemma is not silently suppressed.
    """

    text = str(record.get("text") or "").strip()
    if "<k>" in text.casefold():
        return "SAOL14 source issue: <k> markup in text field"

    key = (
        str(record.get("normaliserat_ord") or record.get("lemma") or "")
        .strip()
        .casefold(),
        text,
        _clean_stycke(record.get("stycke")),
    )
    return _KNOWN_LEMMA_ONLY_ROWS.get(key)
