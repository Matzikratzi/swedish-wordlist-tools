from __future__ import annotations

import re

_FORM = r"[a-zåäöéü]+"
_HTML = re.compile(r"<[^>]+>")
_REPLACEMENT = re.compile(rf"(?<!\+)-({_FORM})", re.IGNORECASE)


def bar_prefix(stycke: str, lemma: str) -> str:
    """Return the fixed part before the final SAOL vertical bar.

    Middle dots and other article markup are ignored.  The prefix is accepted
    only when it is an actual prefix of the normalized lemma.
    """

    cleaned = _HTML.sub("", str(stycke or "")).casefold()
    if "|" not in cleaned:
        return ""
    prefix = "".join(cleaned.split("|")[:-1])
    prefix = re.sub(r"^\d+", "", prefix)
    prefix = "".join(char for char in prefix if char.isalpha() or char == "-")
    folded_lemma = str(lemma or "").casefold()
    return prefix if prefix and folded_lemma.startswith(prefix) else ""


def replacement_tails(notation: str) -> frozenset[str]:
    """Return lexical tails written with SAOL's replacement hyphen."""

    return frozenset(match.casefold() for match in _REPLACEMENT.findall(str(notation or "")))


def restore_replacement_bar_prefix(
    *,
    stycke: str,
    lemma: str,
    notation: str,
    written_form: str,
) -> str:
    """Restore a compound prefix lost while realizing a ``-tail`` form.

    This is a generation invariant, not a second inflection pass.  It only
    changes a form when the generated form is exactly one of the replacement
    tails written in the SAOL notation and the article supplies a usable bar.
    """

    form = str(written_form or "").casefold()
    prefix = bar_prefix(stycke, lemma)
    if not prefix or form.startswith(prefix):
        return form
    if form not in replacement_tails(notation):
        return form
    return prefix + form
