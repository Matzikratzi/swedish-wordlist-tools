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


def replay_generated_form(
    *,
    lemma: str,
    stycke: str,
    written_form: str,
    slot: str,
    provenance: str,
    source_token: str,
) -> ReplayResult:
    """Replay one generated form from its stored primitive SAOL operation.

    The function does not inspect the full notation and does not choose a slot.
    It only applies the operation token already stored by the canonical
    generator. This makes it a consistency check, not a second generator.
    """

    provenance = str(provenance or "")
    token = str(source_token or "").strip().casefold()
    expected = str(written_form or "").casefold()
    base = str(lemma or "").casefold()

    if provenance == "lemma":
        replayed = base
    elif provenance == "explicit":
        # Some explicit alternative stems are represented by a whole branch,
        # such as ``facetterat +e``. They cannot be replayed from one primitive
        # token without interpreting the paradigm again.
        operation = parse_form_operation(token)
        if operation is None or " " in token:
            return ReplayResult("unsupported", None)
        replayed = apply_form_operation(base, operation)
    elif provenance in {"append", "replace_tail"}:
        operation = parse_form_operation(token)
        if operation is None:
            return ReplayResult("unsupported", None)
        replayed = apply_form_operation(
            base,
            operation,
            append=lambda word, suffix: _append_adjective(word, suffix, slot=slot),
            replace_tail=lambda word, tail: _replace_from_bar(word, stycke, tail),
        )
    else:
        return ReplayResult("unsupported", None)

    if replayed is None:
        return ReplayResult("unsupported", None)
    replayed = replayed.casefold()
    return ReplayResult("match" if replayed == expected else "mismatch", replayed)
