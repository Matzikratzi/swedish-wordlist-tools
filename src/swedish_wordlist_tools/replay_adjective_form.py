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
    notation: str = "",
) -> ReplayResult:
    """Replay one generated form from its stored primitive SAOL operation.

    The function does not choose a slot or generate a paradigm. It applies the
    stored operation token to the stored lemma/stycke context. Parallel
    paradigms are reported as unsupported because their active base may be an
    alternative stem rather than the entry lemma.
    """

    provenance = str(provenance or "")
    token = str(source_token or "").strip().casefold()
    expected = str(written_form or "").casefold()
    base = str(lemma or "").casefold()
    normalized_notation = " ".join(str(notation or "").casefold().split())

    if provenance == "lemma":
        replayed = base
    elif provenance == "explicit":
        operation = parse_form_operation(token)
        if operation is None or " " in token:
            return ReplayResult("unsupported", None)
        replayed = apply_form_operation(base, operation)
    elif provenance in {"append", "replace_tail"}:
        # In a parallel paradigm the operation may apply to an alternative
        # stem reconstructed by the adjective parser. Replaying it from the
        # entry lemma alone would create false mismatches.
        if " _ " in normalized_notation:
            return ReplayResult("unsupported", None)

        operation = parse_form_operation(token)
        if operation is None:
            return ReplayResult("unsupported", None)

        if provenance == "replace_tail":
            # A documented lodstreck is authoritative. Do not let the generic
            # overlap fallback choose an earlier, equally long match such as
            # the initial ``fö`` in ``förstfödd``.
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
    else:
        return ReplayResult("unsupported", None)

    if replayed is None:
        return ReplayResult("unsupported", None)
    replayed = replayed.casefold()
    return ReplayResult("match" if replayed == expected else "mismatch", replayed)
