from __future__ import annotations

import re

_OPERATION = re.compile(r"[+-]?[a-zåäöéü]+", re.IGNORECASE)
_LABELS = {"pl", "n", "best", "mask", "komp", "superl"}


def _tokens(notation: str) -> tuple[str, ...]:
    return tuple(_OPERATION.findall(str(notation or "").casefold()))


def _operation_kind(token: str) -> str:
    if token.startswith("-"):
        return "replace_tail"
    if token.startswith("+"):
        return "append"
    return "explicit"


def slot_operation_token(slot: str, notation: str) -> str | None:
    """Return the SAOL token that supplies one generated adjective slot."""

    normalized = " ".join(str(notation or "").casefold().split())
    first_branch = normalized.split(" _ ", 1)[0]
    lexical = [token for token in _tokens(first_branch) if token not in _LABELS]

    if slot == "neuter_singular" and lexical:
        return lexical[0]
    if slot == "definite_or_plural" and len(lexical) >= 2:
        return lexical[1]
    if (
        slot == "definite_or_plural"
        and normalized.startswith(("pl. ", "best. "))
        and lexical
    ):
        return lexical[-1]
    if slot == "comparative":
        match = re.search(r"komp\.\s+([+-]?[a-zåäöéü]+)", normalized)
        return match.group(1) if match else None
    if slot == "superlative":
        match = re.search(r"superl\.\s+([+-]?[a-zåäöéü]+)", normalized)
        return match.group(1) if match else None
    return None


def form_provenance(*, written_form: str, lemma: str, slot: str, notation: str) -> str:
    """Describe how a canonical generated form was obtained.

    This function is called by the generator. Validators and mismatch reports
    consume the stored value and must not infer it by parsing notation again.
    """

    form = str(written_form or "").casefold()
    folded_lemma = str(lemma or "").casefold()
    tokens = _tokens(notation)

    if form == folded_lemma:
        return "lemma"
    if form in {token for token in tokens if not token.startswith(("+", "-"))}:
        return "explicit"

    token = slot_operation_token(slot, notation)
    if token:
        return _operation_kind(token)

    return "unknown"
