from __future__ import annotations

from .adjective_slots import AdjectiveForm, AdjectiveSlots


def expand_adjective_forms(slots: AdjectiveSlots) -> AdjectiveSlots:
    """Materialize regular inflection of already interpreted adjective slot forms.

    SAOL can give the predicative/indefinite superlative as one atom (for example
    ``minst``) while the ordinary definite/plural and masculine definite forms are
    regular inflections of that atom.  This layer deliberately runs *after* row
    interpretation: it does not reinterpret SAOL notation and it contains no
    lemma-specific exceptions.
    """

    forms = list(slots.forms)
    seen = {(form.written_form, form.slot) for form in forms}

    for form in slots.forms:
        if form.slot != "superlative":
            continue
        base = form.written_form
        if not base.endswith("st"):
            continue
        for written_form, slot in (
            (base + "a", "superlative_definite_or_plural"),
            (base + "e", "superlative_masculine_definite"),
        ):
            marker = (written_form, slot)
            if marker not in seen:
                forms.append(AdjectiveForm(written_form, slot, provenance="derived_inflection"))
                seen.add(marker)

    if tuple(forms) == slots.forms:
        return slots
    return AdjectiveSlots(
        lemma=slots.lemma,
        forms=tuple(forms),
        rule=slots.rule,
        restrictions=slots.restrictions,
    )
