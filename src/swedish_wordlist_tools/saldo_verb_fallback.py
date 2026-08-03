from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

from .lexeme_slots import LexemeSlots, SlotForm, build_lexeme_slots

_PASSIVE_MARKERS = {"pass", "passiv", "s-form", "sform"}


def _normalise_msd(value: object) -> str:
    return re.sub(r"[^a-zåäö0-9]+", " ", str(value or "").casefold()).strip()


def saldo_verb_slot(msd: object) -> str | None:
    """Map an unambiguous SALDO verb MSD label to a supported slot.

    The mapping is intentionally conservative. Passive forms are not imported
    yet, and unknown labels return ``None`` rather than guessing.
    """
    text = _normalise_msd(msd)
    if not text:
        return None
    words = set(text.split())
    if words & _PASSIVE_MARKERS or "passiv" in text:
        return None

    if "pres" in words or "presens" in words:
        return "present"
    if words & {"pret", "preteritum", "imperf", "imperfekt"}:
        return "preterite"
    if "sup" in words or "supinum" in words:
        return "supine"
    if "inf" in words or "infinitiv" in words:
        return "infinitive"
    if "imper" in words or "imperativ" in words:
        return "imperative_active"

    is_perfect_participle = (
        ("perf" in words or "perfekt" in words)
        and ("part" in words or "particip" in words)
    )
    if is_perfect_participle:
        if words & {"pl", "plural"}:
            return "perfect_participle_plural"
        if words & {"neut", "neutrum", "ett"}:
            return "perfect_participle_neuter"
        if words & {"utr", "utrum", "common", "en"}:
            return "perfect_participle_common"
    return None


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


def _tagged_forms(analysis: Mapping[str, Any]) -> Iterable[tuple[str, str]]:
    for item in analysis.get("form_entries", ()):
        if not isinstance(item, Mapping):
            continue
        written = str(item.get("written_form") or item.get("writtenForm") or "").strip()
        msd = str(item.get("msd") or "").strip()
        if written and msd:
            yield written, msd


def select_unique_saldo_verb_analysis(
    lemma: str,
    analyses: Iterable[Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    """Select one exact VERB analysis, rejecting homonym ambiguity."""
    key = lemma.strip().casefold()
    candidates = [
        analysis
        for analysis in analyses
        if _analysis_upos(analysis) == "VERB" and key in _analysis_lemmas(analysis)
    ]
    return candidates[0] if len(candidates) == 1 else None


def add_saldo_verb_fallback(
    current: LexemeSlots,
    analyses: Iterable[Mapping[str, Any]],
) -> LexemeSlots:
    """Fill only missing verb slots from one exact, tagged SALDO analysis.

    Existing row-derived or compound-head-derived slots are never overwritten.
    A SALDO slot is imported only when the selected analysis has tagged forms
    for that slot and no form already exists in the slot.
    """
    if current.upos != "VERB":
        return current
    analysis = select_unique_saldo_verb_analysis(current.lemma, analyses)
    if analysis is None:
        return current

    by_slot: dict[str, list[str]] = {}
    for written, msd in _tagged_forms(analysis):
        slot = saldo_verb_slot(msd)
        if slot is None:
            continue
        values = by_slot.setdefault(slot, [])
        if written not in values:
            values.append(written)

    forms = list(current.forms)
    changed = False
    source_id = _analysis_id(analysis)
    for slot, written_forms in by_slot.items():
        if current.forms_for(slot):
            continue
        for written in written_forms:
            forms.append(
                SlotForm(
                    slot,
                    written,
                    f"saldo:{source_id}",
                    "saldo",
                    source_id,
                )
            )
            changed = True

    if not changed:
        return current
    metadata = dict(current.metadata)
    metadata["saldo_fallback_lexeme"] = source_id
    return build_lexeme_slots(
        lemma=current.lemma,
        upos=current.upos,
        notation=current.notation,
        forms=forms,
        metadata=metadata,
    )
