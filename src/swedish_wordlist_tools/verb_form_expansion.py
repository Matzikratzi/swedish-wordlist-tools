from __future__ import annotations

from .lexeme_slots import LexemeSlots, SlotForm


def _with_additions(slots: LexemeSlots, additions: tuple[SlotForm, ...]) -> LexemeSlots:
    forms = list(slots.forms)
    seen = {(form.written_form, form.slot) for form in forms}
    for form in additions:
        marker = (form.written_form, form.slot)
        if marker not in seen:
            forms.append(form)
            seen.add(marker)
    return LexemeSlots(
        lemma=slots.lemma,
        upos=slots.upos,
        notation=slots.notation,
        forms=tuple(forms),
        metadata=slots.metadata,
    )


def expand_regular_first_conjugation(slots: LexemeSlots) -> LexemeSlots:
    """Materialize the full paradigm licensed by SAOL ``+de +t``.

    The compact notation identifies a regular first-conjugation verb.  The
    expansion is mechanical and uses no external lexicon or lemma-specific
    exception.  Genitives of participles are deliberately outside this layer.
    """

    if slots.upos != "VERB" or slots.notation.strip() != "+de +t":
        return slots
    lemma = slots.lemma
    if not lemma.endswith("a"):
        return slots
    preterite = slots.first("preterite")
    supine = slots.first("supine")
    if preterite is None or supine is None:
        return slots

    stem = lemma[:-1]
    additions = (
        SlotForm("present", lemma + "r", "+r", "derived_inflection", "regular_first_conjugation"),
        SlotForm("imperative", lemma, "+", "derived_inflection", "regular_first_conjugation"),
        SlotForm("infinitive_passive", lemma + "s", "+s", "derived_inflection", "regular_first_conjugation"),
        SlotForm("present_passive", lemma + "s", "+s", "derived_inflection", "regular_first_conjugation"),
        SlotForm("preterite_passive", preterite + "s", "+s", "derived_inflection", "regular_first_conjugation"),
        SlotForm("supine_passive", supine + "s", "+s", "derived_inflection", "regular_first_conjugation"),
        SlotForm("present_participle", stem + "ande", "+nde", "derived_inflection", "regular_first_conjugation"),
        SlotForm("perfect_participle_common", stem + "ad", "+d", "derived_inflection", "regular_first_conjugation"),
        SlotForm("perfect_participle_neuter", supine, "+t", "derived_inflection", "regular_first_conjugation"),
        SlotForm("perfect_participle_plural", preterite, "+de", "derived_inflection", "regular_first_conjugation"),
    )
    return _with_additions(slots, additions)


def expand_stem_preserving_second_conjugation(slots: LexemeSlots) -> LexemeSlots:
    """Add present and imperative where SAOL proves the regular stem pattern.

    A complete row with preterite ``stem+de/te`` and supine ``stem+t`` licenses
    the stem-preserving second-conjugation present and imperative mechanically.
    Rows with stem alternation, alternatives, truncation, or explicit core forms
    are deliberately left untouched.
    """

    if slots.upos != "VERB" or slots.metadata.get("source_truncated") == "true":
        return slots
    lemma = slots.lemma
    if not lemma.endswith("a"):
        return slots
    if slots.forms_for("present") or slots.forms_for("imperative"):
        return slots
    preterites = slots.forms_for("preterite")
    supines = slots.forms_for("supine")
    if len(preterites) != 1 or len(supines) != 1:
        return slots

    stem = lemma[:-1]
    if preterites[0] not in {stem + "de", stem + "te"} or supines[0] != stem + "t":
        return slots

    additions = (
        SlotForm(
            "present",
            stem + "er",
            "stem+er",
            "derived_inflection",
            "stem_preserving_second_conjugation",
        ),
        SlotForm(
            "imperative",
            stem,
            "stem",
            "derived_inflection",
            "stem_preserving_second_conjugation",
        ),
    )
    return _with_additions(slots, additions)
