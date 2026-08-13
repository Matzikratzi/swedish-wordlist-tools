from __future__ import annotations

from dataclasses import dataclass

from .saol_boundaries import bar_prefix
from .saol_notation import apply_form_operation, parse_form_operation


@dataclass(frozen=True)
class ReplayResult:
    status: str
    replayed_form: str | None


def _append_adjective(base: str, suffix: str, *, slot: str) -> str | None:
    if not suffix.isalpha():
        return None
    if suffix == "t" and slot == "neuter_singular":
        if base.endswith(("rd", "ld")):
            return base[:-1] + "t"
        if base.endswith("d"):
            return base[:-1] + "tt"
    return base + suffix


def _replace_from_bar(lemma: str, stycke: str, tail: str) -> str | None:
    prefix = bar_prefix(stycke, lemma)
    return prefix + tail if prefix else None


def _inverse_append_base(form: str, suffix: str, *, slot: str) -> str | None:
    if not suffix or not form.endswith(suffix):
        return None
    candidate = form[: -len(suffix)]
    replayed = _append_adjective(candidate, suffix, slot=slot)
    return candidate if replayed == form else None


def replay_generated_form(
    *,
    lemma: str,
    stycke: str,
    written_form: str,
    slot: str,
    provenance: str,
    source_token: str,
    notation: str = "",
    operation_base: str = "",
) -> ReplayResult:
    """Replay one generated form from its stored primitive SAOL operation.

    The function does not choose a slot or generate a paradigm. It applies the
    stored token to its stored operation base. For older artifacts without that
    field, append bases can be recovered conservatively from the finished form.
    """

    provenance = str(provenance or "")
    token = str(source_token or "").strip().casefold()
    expected = str(written_form or "").casefold()
    lemma_base = str(lemma or "").casefold()
    stored_base = str(operation_base or "").casefold()
    base = stored_base or lemma_base

    if provenance == "lemma":
        replayed = base
    elif provenance == "explicit":
        # A compound source token such as ``facetterat +e`` documents the
        # alternative paradigm from which the common form was reconstructed.
        # The canonical generator stores that reconstructed form itself as the
        # operation base, so replay consists of verifying the stored base.
        if " " in token:
            if not stored_base:
                return ReplayResult("unsupported", None)
            replayed = stored_base
        else:
            operation = parse_form_operation(token)
            if operation is None:
                return ReplayResult("unsupported", None)
            replayed = apply_form_operation(base, operation)
    elif provenance in {"append", "replace_tail"}:
        operation = parse_form_operation(token)
        if operation is None:
            return ReplayResult("unsupported", None)

        if provenance == "replace_tail":
            replayed = _replace_from_bar(base, stycke, operation.value)
            if replayed is None:
                replayed = apply_form_operation(base, operation)
        else:
            replayed = apply_form_operation(
                base,
                operation,
                append=lambda word, suffix: _append_adjective(
                    word, suffix, slot=slot
                ),
            )
            if replayed != expected and not stored_base:
                inverse_base = _inverse_append_base(
                    expected, operation.value, slot=slot
                )
                if inverse_base:
                    replayed = _append_adjective(
                        inverse_base, operation.value, slot=slot
                    )
    else:
        return ReplayResult("unsupported", None)

    if replayed is None:
        return ReplayResult("unsupported", None)
    replayed = replayed.casefold()
    return ReplayResult("match" if replayed == expected else "mismatch", replayed)
