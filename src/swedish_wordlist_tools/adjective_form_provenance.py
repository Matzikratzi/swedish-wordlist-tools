from __future__ import annotations

import re
from dataclasses import dataclass

_OPERATION = re.compile(r"[+-]?[a-zåäöéü]+", re.IGNORECASE)
_LABELS = {"pl", "n", "best", "mask", "komp", "superl"}


@dataclass(frozen=True)
class FormProvenance:
    kind: str
    source_token: str = ""


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
    # In notation such as ``n. +, +a`` the unchanged neuter is written as a
    # bare plus sign, which is intentionally absent from _OPERATION. The sole
    # lexical operation token therefore supplies the plural slot.
    if slot == "definite_or_plural" and normalized.startswith("n. +,") and lexical:
        return lexical[-1]
    if slot == "comparative":
        match = re.search(r"komp\.\s+([+-]?[a-zåäöéü]+)", normalized)
        return match.group(1) if match else None
    if slot == "superlative":
        match = re.search(r"superl\.\s+([+-]?[a-zåäöéü]+)", normalized)
        return match.group(1) if match else None
    return None


def form_provenance_details(
    *, written_form: str, lemma: str, slot: str, notation: str
) -> FormProvenance:
    """Describe how one canonical adjective form was obtained.

    The generator stores both the operation kind and the exact SAOL token.
    Validators and reports consume these fields and do not parse notation again.
    """

    form = str(written_form or "").casefold()
    folded_lemma = str(lemma or "").casefold()
    normalized = " ".join(str(notation or "").casefold().split())
    tokens = _tokens(normalized)

    if form == folded_lemma:
        return FormProvenance("lemma")
    explicit_tokens = {token for token in tokens if not token.startswith(("+", "-"))}
    if form in explicit_tokens:
        return FormProvenance("explicit", form)

    token = slot_operation_token(slot, normalized)
    if token:
        return FormProvenance(_operation_kind(token), token)

    # Parallel paradigms separated by ``_`` may imply an alternative common
    # form from an explicitly written alternative neuter/plural pair, e.g.
    # ``fasetterat +e _ facetterat +e`` -> ``facetterad``. The alternative
    # stem is supplied explicitly by SAOL, but no single surface token equals
    # the reconstructed common form.
    if slot == "common_singular" and " _ " in normalized:
        return FormProvenance("explicit", normalized.split(" _ ", 1)[1])

    return FormProvenance("unknown")


def form_provenance(*, written_form: str, lemma: str, slot: str, notation: str) -> str:
    """Backward-compatible shorthand returning only the provenance kind."""

    return form_provenance_details(
        written_form=written_form,
        lemma=lemma,
        slot=slot,
        notation=notation,
    ).kind
