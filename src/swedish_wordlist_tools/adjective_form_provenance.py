from __future__ import annotations

import re
from dataclasses import dataclass

from .saol_boundaries import bar_prefix
from .saol_notation import apply_form_operation, parse_form_operation

_OPERATION = re.compile(r"[+-]?[a-zåäöéü]+", re.IGNORECASE)
_LABELS = {"pl", "n", "best", "mask", "komp", "superl"}


@dataclass(frozen=True)
class FormProvenance:
    kind: str
    source_token: str = ""
    operation_base: str = ""


def _tokens(notation: str) -> tuple[str, ...]:
    return tuple(_OPERATION.findall(str(notation or "").casefold()))


def _operation_kind(token: str) -> str:
    if token.startswith("-"):
        return "replace_tail"
    if token.startswith("+"):
        return "append"
    return "explicit"


def _append_adjective(base: str, suffix: str, *, slot: str) -> str | None:
    if not suffix.isalpha():
        return None
    if suffix == "t" and slot == "neuter_singular":
        if base.endswith(("rd", "ld")):
            return base[:-1] + "t"
        if base.endswith("d"):
            return base[:-1] + "tt"
    return base + suffix


def _apply_candidate(base: str, token: str, *, slot: str, stycke: str) -> str | None:
    operation = parse_form_operation(token)
    if operation is None:
        return None
    prefix = bar_prefix(stycke, base)
    return apply_form_operation(
        base,
        operation,
        append=lambda word, suffix: _append_adjective(word, suffix, slot=slot),
        replace_tail=(lambda _word, tail: prefix + tail) if prefix else None,
    )


def _inverse_append_base(form: str, token: str, *, slot: str) -> str | None:
    if not token.startswith("+") or token.startswith("+-"):
        return None
    suffix = token[1:]
    if not suffix or not form.endswith(suffix):
        return None
    base = form[: -len(suffix)]
    return base if _apply_candidate(base, token, slot=slot, stycke="") == form else None


def slot_operation_token(slot: str, notation: str) -> str | None:
    """Return the first SAOL token that conventionally supplies one slot."""

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
    if slot == "definite_or_plural" and normalized.startswith("n. +,") and lexical:
        return lexical[-1]
    if slot == "comparative":
        match = re.search(r"komp\.\s+([+-]?[a-zåäöéü]+)", normalized)
        return match.group(1) if match else None
    if slot == "superlative":
        match = re.search(r"superl\.\s+([+-]?[a-zåäöéü]+)", normalized)
        return match.group(1) if match else None
    return None


def _matching_operation(
    *, form: str, lemma: str, slot: str, notation: str, stycke: str
) -> FormProvenance | None:
    """Find the operation token and base that actually reproduce ``form``.

    All alternative branches are considered. This avoids attaching the first
    branch's token to a form generated from a later alternative paradigm.
    """

    operation_tokens = [
        token for token in _tokens(notation)
        if token not in _LABELS and token.startswith(("+", "-"))
    ]
    for token in operation_tokens:
        replayed = _apply_candidate(lemma, token, slot=slot, stycke=stycke)
        if replayed == form:
            return FormProvenance(_operation_kind(token), token, lemma)

    for token in operation_tokens:
        base = _inverse_append_base(form, token, slot=slot)
        if base:
            return FormProvenance("append", token, base)

    return None


def form_provenance_details(
    *,
    written_form: str,
    lemma: str,
    slot: str,
    notation: str,
    stycke: str = "",
) -> FormProvenance:
    """Describe how one canonical adjective form was obtained.

    The generator stores operation kind, exact SAOL token, and operation base.
    Validators and reports consume these fields and do not parse notation again.
    """

    form = str(written_form or "").casefold()
    folded_lemma = str(lemma or "").casefold()
    normalized = " ".join(str(notation or "").casefold().split())
    tokens = _tokens(normalized)

    if form == folded_lemma:
        return FormProvenance("lemma", operation_base=folded_lemma)
    explicit_tokens = {token for token in tokens if not token.startswith(("+", "-"))}
    if form in explicit_tokens:
        return FormProvenance("explicit", form, form)

    matched = _matching_operation(
        form=form,
        lemma=folded_lemma,
        slot=slot,
        notation=normalized,
        stycke=stycke,
    )
    if matched:
        return matched

    token = slot_operation_token(slot, normalized)
    if token:
        return FormProvenance(_operation_kind(token), token, folded_lemma)

    if slot == "common_singular" and " _ " in normalized:
        return FormProvenance("explicit", normalized.split(" _ ", 1)[1], form)

    return FormProvenance("unknown")


def form_provenance(*, written_form: str, lemma: str, slot: str, notation: str) -> str:
    """Backward-compatible shorthand returning only the provenance kind."""

    return form_provenance_details(
        written_form=written_form,
        lemma=lemma,
        slot=slot,
        notation=notation,
    ).kind
