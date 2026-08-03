from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from .lexeme_slots import LexemeSlots, SlotForm, build_lexeme_slots


def _analysis_id(analysis: Mapping[str, Any]) -> str:
    return str(analysis.get("id") or "")


def _analysis_upos(analysis: Mapping[str, Any]) -> str:
    return str(analysis.get("upos") or "").upper()


def _analysis_lemmas(analysis: Mapping[str, Any]) -> set[str]:
    return {
        str(value).strip().casefold()
        for value in analysis.get("lemmas", ())
        if str(value).strip()
    }


def exact_saldo_verb_analyses(
    lemma: str,
    analyses: Iterable[Mapping[str, Any]],
) -> tuple[Mapping[str, Any], ...]:
    """Return every exact VERB analysis for ``lemma``.

    Homonymous analyses are intentionally retained. For a game word list their
    union still consists of forms attested by SALDO; grammatical disambiguation
    is not required merely to admit a written word form.
    """
    key = lemma.strip().casefold()
    return tuple(
        analysis
        for analysis in analyses
        if _analysis_upos(analysis) == "VERB" and key in _analysis_lemmas(analysis)
    )


def _safe_written_forms(analysis: Mapping[str, Any]) -> Iterable[str]:
    for value in analysis.get("forms", ()):
        written = str(value).strip()
        if not written or written.endswith("-"):
            continue
        yield written


def add_saldo_attested_forms(
    current: LexemeSlots,
    analyses: Iterable[Mapping[str, Any]],
) -> LexemeSlots:
    """Add exact-lemma SALDO forms without guessing their grammatical slot.

    Existing row-derived forms remain untouched. New SALDO words are stored in
    the generic ``saldo_attested`` slot and carry form-level provenance. This is
    sufficient for game-word-list generation while preserving the more precise
    slots already interpreted from SAOL.
    """
    if current.upos != "VERB":
        return current
    selected = exact_saldo_verb_analyses(current.lemma, analyses)
    if not selected:
        return current

    existing_words = set(current.written_forms())
    supporting_ids: dict[str, list[str]] = {}
    for analysis in selected:
        source_id = _analysis_id(analysis)
        for written in _safe_written_forms(analysis):
            ids = supporting_ids.setdefault(written, [])
            if source_id and source_id not in ids:
                ids.append(source_id)

    forms = list(current.forms)
    changed = False
    for written in sorted(supporting_ids, key=str.casefold):
        if written in existing_words:
            continue
        source_ids = ",".join(supporting_ids[written])
        forms.append(
            SlotForm(
                "saldo_attested",
                written,
                f"saldo:{source_ids}",
                "saldo",
                source_ids,
            )
        )
        existing_words.add(written)
        changed = True

    if not changed:
        return current
    metadata = dict(current.metadata)
    metadata["saldo_fallback_lexemes"] = ",".join(
        source_id
        for source_id in (_analysis_id(analysis) for analysis in selected)
        if source_id
    )
    return build_lexeme_slots(
        lemma=current.lemma,
        upos=current.upos,
        notation=current.notation,
        forms=forms,
        metadata=metadata,
    )


# Backwards-compatible name while callers migrate to the game-oriented API.
add_saldo_verb_fallback = add_saldo_attested_forms
