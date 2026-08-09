from __future__ import annotations

import re
import unicodedata
from typing import Any

_SUP_ELEMENT_RE = re.compile(r"<sup\b[^>]*>.*?</sup>", re.IGNORECASE | re.DOTALL)
_HTML_TAG_RE = re.compile(r"<[^>]*>")
_SPACE_RE = re.compile(r"\s+")


def clean_saol_word(value: object) -> str:
    """Return the written SAOL headword without presentation separators.

    ``ord`` is the printed/written headword carrier.  Middle dots mark
    syllabification and vertical bars mark compound boundaries; neither is part
    of the spelling.  Keep ordinary hyphens and spaces because they can be part
    of the actual headword.
    """

    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value))
    if not text or text == "(null)":
        return ""
    text = _SUP_ELEMENT_RE.sub("", text)
    text = _HTML_TAG_RE.sub("", text)
    text = text.replace("\u00ad", "").replace("·", "").replace("|", "")
    return _SPACE_RE.sub(" ", text).strip()


def surface_lemma(record: dict[str, Any]) -> str:
    """Return the row's actual written lemma, falling back to normalization.

    ``normaliserat_ord`` can intentionally collapse spelling variants onto one
    normalized lemma.  For word-list generation we must instead inflect the
    explicit written variant in ``ord`` when it is available, e.g. ``acne``
    alongside normalized ``akne``.
    """

    written = clean_saol_word(record.get("ord"))
    if written:
        return written
    return clean_saol_word(record.get("normaliserat_ord"))
